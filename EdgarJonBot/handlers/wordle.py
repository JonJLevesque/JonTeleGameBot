"""Competitive daily Wordle: /wordle — the real NYT puzzle, played in-bot.

The bot fetches the official NYT word of the day (public endpoint, cached;
deterministic fallback list if unreachable), so both of you play the same
puzzle as the rest of the world — but inside Telegram: each plays privately
in a DM (/wordle, then type 5-letter guesses); a finished grid (squares only)
auto-posts to the shared group; when both have finished, the bot calls the
day's head-to-head. /wordle in the group shows standings and all-time stats.
"""
import html
import json
import logging
from collections import Counter
from datetime import date, time as dtime, timedelta
from pathlib import Path

import httpx
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import TelegramError
from telegram.ext import ApplicationHandlerStop, CommandHandler, ContextTypes, MessageHandler, filters

import db
from .common import LOCAL_TZ

log = logging.getLogger("edgarjon.wordle")

EPOCH = date(2021, 6, 19)
NYT_URL = "https://www.nytimes.com/svc/wordle/v2/{day}.json"
MAX_GUESSES = 6
GROUP_TYPES = ("group", "supergroup")
_DATA = Path(__file__).resolve().parent.parent / "data"
_answers: list[str] | None = None
_allowed: set[str] | None = None


def _load_words() -> tuple[list[str], set[str]]:
    global _answers, _allowed
    if _answers is None:
        try:
            _answers = (_DATA / "wordle_answers.txt").read_text().split()
        except OSError:
            _answers = []
        try:
            extra = (_DATA / "wordle_allowed.txt").read_text().split()
        except OSError:
            extra = []
        _allowed = set(_answers) | set(extra)
    return _answers, _allowed


async def _todays_word() -> tuple[str, int, str]:
    today = date.today()
    day = today.isoformat()
    number = (today - EPOCH).days
    row = db.wordle_day(day)
    if row:
        return day, row["number"], row["word"]
    word = None
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(NYT_URL.format(day=day))
            r.raise_for_status()
            data = r.json()
            solution = data.get("solution", "")
            if len(solution) == 5 and solution.isalpha():
                word = solution.lower()
                number = int(data.get("days_since_launch", number))
    except (httpx.HTTPError, ValueError):
        log.warning("NYT wordle fetch failed; using fallback list")
    if word is None:
        answers, _ = _load_words()
        if not answers:
            raise RuntimeError("no word source available")
        word = answers[number % len(answers)]
    db.save_wordle_day(day, number, word)
    return day, number, word


def score_guess(guess: str, word: str) -> list[str]:
    """'g' green, 'y' yellow, 'b' gray — duplicate-letter safe."""
    result = ["b"] * 5
    remaining = Counter()
    for i, (g, w) in enumerate(zip(guess, word)):
        if g == w:
            result[i] = "g"
        else:
            remaining[w] += 1
    for i, g in enumerate(guess):
        if result[i] == "b" and remaining[g] > 0:
            result[i] = "y"
            remaining[g] -= 1
    return result


_SQ = {"g": "🟩", "y": "🟨", "b": "⬛"}


def _grid(guesses, word, letters):
    rows = []
    for g in guesses:
        row = "".join(_SQ[c] for c in score_guess(g, word))
        if letters:
            row += "  " + " ".join(g.upper())
        rows.append(row)
    return "\n".join(rows)


def _absent_letters(guesses, word) -> str:
    return " ".join(c.upper() for c in sorted({c for g in guesses for c in g} - set(word)))


def streak(user_id: int, today: date | None = None) -> int:
    """Consecutive finished days ending today or yesterday."""
    days = {d for d, _, _ in db.wordle_user_days(user_id)}
    cursor = today or date.today()
    if cursor.isoformat() not in days:
        cursor -= timedelta(days=1)
    n = 0
    while cursor.isoformat() in days:
        n += 1
        cursor -= timedelta(days=1)
    return n


def cost(play) -> int:
    """Guesses used, or MAX+1 for a loss — lower wins the duel."""
    return len(json.loads(play["guesses"])) if play["won"] else MAX_GUESSES + 1


def duel_result(a, b) -> tuple[object | None, int, int]:
    """(winner_row or None for a tie, cost_a, cost_b)."""
    ca, cb = cost(a), cost(b)
    if ca == cb:
        return None, ca, cb
    return (a if ca < cb else b), ca, cb


async def _announce_finish(context, user_id, first_name, day, number, guesses, won, word):
    score = f"{len(guesses)}/{MAX_GUESSES}" if won else f"X/{MAX_GUESSES}"
    for chat_id in db.chats_for_user(user_id):
        if len(db.chat_members(chat_id)) < 2:
            continue
        try:
            await context.bot.send_message(
                chat_id, f"🟩 <b>{html.escape(first_name)}</b> finished Wordle #{number:,}: <b>{score}</b>\n{_grid(guesses, word, False)}",
                parse_mode="HTML")
        except TelegramError:
            continue
        if db.wordle_duel(chat_id, day):
            continue
        finishers = db.wordle_finishers(chat_id, day)
        if len(finishers) < 2:
            continue
        a, b = finishers[0], finishers[1]
        winner, ca, cb = duel_result(a, b)
        if winner is None:
            db.save_wordle_duel(chat_id, day, None)
            text = f"🤝 Dead heat on Wordle #{number:,} — {html.escape(a['first_name'])} and {html.escape(b['first_name'])} both went {score}."
        else:
            db.save_wordle_duel(chat_id, day, winner["user_id"])
            wins = db.wordle_duel_wins(chat_id, winner["user_id"])
            lo, hi = min(ca, cb), max(ca, cb)
            text = (f"🏅 <b>{html.escape(winner['first_name'])}</b> takes today's Wordle duel "
                    f"({lo} vs {hi if hi <= MAX_GUESSES else 'X'}) — {wins} duel win{'s' if wins != 1 else ''} all-time.")
        try:
            await context.bot.send_message(chat_id, text, parse_mode="HTML")
        except TelegramError:
            pass


async def _begin_dm_game(context, user) -> bool:
    day, number, word = await _todays_word()
    play = db.wordle_play(user.id, day)
    guesses = json.loads(play["guesses"]) if play else []
    if play and play["done"]:
        s = f"{len(guesses)}/{MAX_GUESSES}" if play["won"] else f"X/{MAX_GUESSES}"
        text = f"You already finished Wordle #{number:,} today: <b>{s}</b>\n{_grid(guesses, word, True)}\nNew word at midnight. 🌙"
    else:
        if play is None:
            db.save_wordle_play(user.id, day, user.first_name, [], False, False)
        text = (f"🟩 <b>Wordle #{number:,}</b> — same word as today's NYT puzzle.\n"
                f"Type a 5-letter word. {MAX_GUESSES} tries; your grid auto-posts to the group when you're done.")
        if guesses:
            text += f"\n\nYour board so far:\n{_grid(guesses, word, True)}"
    try:
        await context.bot.send_message(user.id, text, parse_mode="HTML")
        return True
    except TelegramError:
        return False


async def begin_from_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _begin_dm_game(context, update.effective_user)


async def wordle_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat, msg, user = update.effective_chat, update.effective_message, update.effective_user
    day, number, word = await _todays_word()
    if chat.type in GROUP_TYPES:
        lines = [f"🟩 <b>Wordle #{number:,}</b> — today's standings"]
        finishers = {p["user_id"]: p for p in db.wordle_finishers(chat.id, day)}
        for m in db.chat_members(chat.id):
            p = finishers.get(m["user_id"])
            s = (f"{len(json.loads(p['guesses']))}/{MAX_GUESSES}" if p["won"] else f"X/{MAX_GUESSES}") if p else "not finished yet"
            line = f"• <b>{html.escape(m['first_name'])}</b>: {s}"
            played = db.wordle_user_days(m["user_id"])
            if played:
                solved = [n for _, w, n in played if w]
                avg = f"{sum(solved) / len(solved):.1f}" if solved else "–"
                wins = db.wordle_duel_wins(chat.id, m["user_id"])
                line += f" · {wins} duel win{'s' if wins != 1 else ''} · streak {streak(m['user_id'])} · avg {avg}"
            lines.append(line)
        safe = html.escape(user.first_name)
        lines.append(f"\n📬 {safe} — today's puzzle is in your DMs." if await _begin_dm_game(context, user)
                     else f"\n{safe} — tap below and hit Start; the puzzle begins automatically.")
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🟩 Play today's Wordle", url=f"https://t.me/{context.bot.username}?start=wordle")]])
        await msg.reply_html("\n".join(lines), reply_markup=kb)
        return
    await _begin_dm_game(context, user)


async def guess_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Private-chat text: a guess when a game is open. Stops other handlers
    (the persona must not answer 'CRANE' with an opinion)."""
    user, msg = update.effective_user, update.effective_message
    text = (msg.text or "").strip().lower()
    if len(text) != 5 or not text.isalpha():
        return
    day, number, word = await _todays_word()
    play = db.wordle_play(user.id, day)
    if play is None or play["done"]:
        return
    _, allowed = _load_words()
    if allowed and text not in allowed and text != word:
        await msg.reply_text(f"“{text.upper()}” isn't in the word list — try another.")
        raise ApplicationHandlerStop
    guesses = json.loads(play["guesses"])
    if text in guesses:
        await msg.reply_text("You already tried that one.")
        raise ApplicationHandlerStop
    guesses.append(text)
    won = text == word
    done = won or len(guesses) >= MAX_GUESSES
    db.save_wordle_play(user.id, day, user.first_name, guesses, done, won)
    board = _grid(guesses, word, True)
    if won:
        praise = ["Genius!", "Magnificent!", "Impressive!", "Splendid!", "Great!", "Phew!"][len(guesses) - 1]
        await msg.reply_html(f"{board}\n\n🎉 <b>{praise}</b> Got it in {len(guesses)}/{MAX_GUESSES}.")
    elif done:
        await msg.reply_html(f"{board}\n\n💀 Out of guesses — it was <b>{word.upper()}</b>.")
    else:
        extra = _absent_letters(guesses, word)
        await msg.reply_html(f"{board}\n\nGuess {len(guesses)}/{MAX_GUESSES}." + (f"  Not in word: {extra}" if extra else ""))
    if done:
        await _announce_finish(context, user.id, user.first_name, day, number, guesses, won, word)
    raise ApplicationHandlerStop


async def _nudge_job(context: ContextTypes.DEFAULT_TYPE):
    day = date.today().isoformat()
    for chat_id in db.chats_with_min_members(2):
        finishers = {p["user_id"] for p in db.wordle_finishers(chat_id, day)}
        if not finishers:
            continue
        members = db.chat_members(chat_id)
        done = [m["first_name"] for m in members if m["user_id"] in finishers]
        missing = [m["first_name"] for m in members if m["user_id"] not in finishers]
        if not missing:
            continue
        try:
            await context.bot.send_message(chat_id, f"⏰ Wordle check: {', '.join(done)} finished today's puzzle; {', '.join(missing)} hasn't played. /wordle")
        except TelegramError:
            pass


def schedule(app) -> None:
    app.job_queue.run_daily(_nudge_job, dtime(20, 30, tzinfo=LOCAL_TZ), name="wordle-nudge")


def get_handlers():
    return [
        CommandHandler("wordle", wordle_cmd),
        MessageHandler(filters.ChatType.PRIVATE & filters.TEXT & ~filters.COMMAND, guess_msg),
    ]
