"""Competitive daily Wordle: /wordle — the real NYT puzzle, played in-bot.

The bot fetches the official NYT word of the day (public endpoint, cached in
SQLite; deterministic fallback list if unreachable), so everyone plays the
same puzzle as the rest of the world — but inside Telegram:

  * each player plays privately in a DM with the bot (/wordle to start,
    then just type 5-letter guesses),
  * the moment a player finishes, their result grid (squares only, no
    letters) is auto-posted to every group chat they share with the bot,
  * when a second member of a chat finishes, the bot announces the day's
    head-to-head: fewer guesses wins and earns a 🍪 (tie = no cookie).

/wordle in a group shows today's standings and all-time stats.
"""
import json
import logging
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

import httpx
from telegram import Update
from telegram.error import TelegramError
from telegram.ext import CommandHandler, ContextTypes, MessageHandler, filters

import db
from .common import GROUP_TYPES

log = logging.getLogger("partybot.wordle")

EPOCH = date(2021, 6, 19)  # Wordle #0; NYT's days_since_launch uses this too
NYT_URL = "https://www.nytimes.com/svc/wordle/v2/{day}.json"
MAX_GUESSES = 6
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
    """(iso_day, puzzle_number, word) for today, cached in the db."""
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
    """Wordle feedback: 'g' green, 'y' yellow, 'b' gray (duplicate-safe)."""
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


def _squares(guess: str, word: str) -> str:
    return "".join(_SQ[c] for c in score_guess(guess, word))


def _grid(guesses: list[str], word: str, letters: bool) -> str:
    rows = []
    for g in guesses:
        row = _squares(g, word)
        if letters:
            row += "  " + " ".join(g.upper())
        rows.append(row)
    return "\n".join(rows)


def _absent_letters(guesses: list[str], word: str) -> str:
    absent = sorted({c for g in guesses for c in g} - set(word))
    return " ".join(c.upper() for c in absent)


def _streak(user_id: int) -> int:
    """Consecutive finished days, ending today or yesterday."""
    days = {d for d, _, _ in db.wordle_user_days(user_id)}
    cursor = date.today()
    if cursor.isoformat() not in days:
        cursor -= timedelta(days=1)
    streak = 0
    while cursor.isoformat() in days:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


async def _announce_finish(context: ContextTypes.DEFAULT_TYPE, user_id: int,
                           first_name: str, day: str, number: int,
                           guesses: list[str], won: bool, word: str) -> None:
    """Post the result to shared group chats and settle head-to-heads."""
    score = f"{len(guesses)}/{MAX_GUESSES}" if won else f"X/{MAX_GUESSES}"
    for chat_id in db.chats_for_user(user_id):
        members = db.chat_members(chat_id)
        if len(members) < 2:
            continue
        try:
            await context.bot.send_message(
                chat_id,
                f"🟩 <b>{first_name}</b> finished Wordle #{number:,}: "
                f"<b>{score}</b>\n{_grid(guesses, word, letters=False)}",
                parse_mode="HTML",
            )
        except TelegramError:
            continue  # bot no longer in this chat
        if db.wordle_duel(chat_id, day):
            continue  # today's duel already settled here
        finishers = db.wordle_finishers(chat_id, day)
        if len(finishers) < 2:
            continue
        a, b = finishers[0], finishers[1]

        def cost(p):
            return len(json.loads(p["guesses"])) if p["won"] else MAX_GUESSES + 1

        ca, cb = cost(a), cost(b)
        if ca == cb:
            db.save_wordle_duel(chat_id, day, None)
            text = (
                f"🤝 Dead heat on Wordle #{number:,} — "
                f"{a['first_name']} and {b['first_name']} both went {score}. "
                f"No cookie today."
            )
        else:
            w, l = (a, b) if ca < cb else (b, a)
            db.save_wordle_duel(chat_id, day, w["user_id"])
            total = db.add_cookies(chat_id, w["user_id"], 1)
            text = (
                f"🏅 <b>{w['first_name']}</b> takes today's Wordle duel "
                f"({min(ca, cb)} vs {max(ca, cb) if max(ca, cb) <= 6 else 'X'} "
                f"guesses) — +1 🍪 (now {total})."
            )
        try:
            await context.bot.send_message(chat_id, text, parse_mode="HTML")
        except TelegramError:
            pass


# ------------------------------------------------------------------ handlers

async def wordle_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    msg = update.effective_message
    user = update.effective_user
    day, number, word = await _todays_word()

    if chat.type in GROUP_TYPES:
        lines = [f"🟩 <b>Wordle #{number:,}</b> — today's standings"]
        finishers = {p["user_id"]: p for p in db.wordle_finishers(chat.id, day)}
        for m in db.chat_members(chat.id):
            p = finishers.get(m["user_id"])
            if p:
                n = len(json.loads(p["guesses"]))
                s = f"{n}/{MAX_GUESSES}" if p["won"] else f"X/{MAX_GUESSES}"
            else:
                s = "not finished yet"
            wins = db.wordle_duel_wins(chat.id, m["user_id"])
            played = db.wordle_user_days(m["user_id"])
            line = f"• <b>{m['first_name']}</b>: {s}"
            if played:
                solved = [n for _, w, n in played if w]
                avg = f"{sum(solved) / len(solved):.1f}" if solved else "–"
                line += (
                    f" · {wins} duel win{'s' if wins != 1 else ''}"
                    f" · streak {_streak(m['user_id'])} · avg {avg}"
                )
            lines.append(line)
        lines.append("\nDM me /wordle to play — same word as the real NYT puzzle!")
        await msg.reply_html("\n".join(lines))
        return

    # Private chat: start or resume today's game.
    play = db.wordle_play(user.id, day)
    guesses = json.loads(play["guesses"]) if play else []
    if play and play["done"]:
        s = f"{len(guesses)}/{MAX_GUESSES}" if play["won"] else f"X/{MAX_GUESSES}"
        await msg.reply_html(
            f"You already finished Wordle #{number:,} today: <b>{s}</b>\n"
            f"{_grid(guesses, word, letters=True)}\n"
            f"New word at midnight! 🌙"
        )
        return
    if play is None:
        db.save_wordle_play(user.id, day, user.first_name, [], False, False)
    text = (
        f"🟩 <b>Wordle #{number:,}</b> — same word as today's NYT puzzle.\n"
        f"Type a 5-letter word to guess. {MAX_GUESSES} tries, results auto-post "
        f"to your group. Good luck!"
    )
    if guesses:
        text += f"\n\nYour board so far:\n{_grid(guesses, word, letters=True)}"
    await msg.reply_html(text)


async def guess_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Private-chat text: treat as a guess when a game is in progress."""
    user = update.effective_user
    msg = update.effective_message
    text = (msg.text or "").strip().lower()
    if len(text) != 5 or not text.isalpha():
        return
    day, number, word = await _todays_word()
    play = db.wordle_play(user.id, day)
    if play is None or play["done"]:
        return  # no game started (or already finished): stay silent
    _, allowed = _load_words()
    if allowed and text not in allowed and text != word:
        await msg.reply_text(f"“{text.upper()}” isn't in the word list — try another.")
        return

    guesses = json.loads(play["guesses"])
    if text in guesses:
        await msg.reply_text("You already tried that one.")
        return
    guesses.append(text)
    won = text == word
    done = won or len(guesses) >= MAX_GUESSES
    db.save_wordle_play(user.id, day, user.first_name, guesses, done, won)

    board = _grid(guesses, word, letters=True)
    if won:
        praise = ["Genius!", "Magnificent!", "Impressive!", "Splendid!", "Great!",
                  "Phew!"][len(guesses) - 1]
        await msg.reply_html(
            f"{board}\n\n🎉 <b>{praise}</b> Got it in {len(guesses)}/{MAX_GUESSES}."
        )
    elif done:
        await msg.reply_html(
            f"{board}\n\n💀 Out of guesses — it was <b>{word.upper()}</b>."
        )
    else:
        extra = _absent_letters(guesses, word)
        await msg.reply_html(
            f"{board}\n\nGuess {len(guesses)}/{MAX_GUESSES}."
            + (f"  Not in word: {extra}" if extra else "")
        )
    if done:
        await _announce_finish(
            context, user.id, user.first_name, day, number, guesses, won, word
        )


def get_handlers():
    return [
        CommandHandler("wordle", wordle_cmd),
        # Group 2: keeps out of the way of taboo's group-1 referee.
        (MessageHandler(
            filters.ChatType.PRIVATE & filters.TEXT & ~filters.COMMAND, guess_msg
        ), 2),
    ]
