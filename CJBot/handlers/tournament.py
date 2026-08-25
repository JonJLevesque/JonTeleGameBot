"""Bracket-of-anything: /tournament — settle any list by knockout vote.

  /tournament Movie Night: Dune, Inception, Parasite, Heat
  /tournament pizza, sushi, tacos, thai        (default title)
  /tournament          -> show the current matchup / status
  /tournament reset    -> wipe the bracket

Same engine and voting rules as the Beautiful Place tournament (bracket.py):
each matchup waits for two different voters; 2-0 advances, 1-1 lets both
live to fight again, and a deadlocked final gets one rematch then a coin.
One custom tournament per chat, persisted in SQLite.
"""
import asyncio
import html
import random
from collections import defaultdict

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.error import TelegramError
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

import db
from .bracket import new_bracket, remaining, start_next_match
from .common import require_group

MAX_ITEMS = 128
_locks: dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)  # per-chat vote lock


def _name(state: dict, item_id: int) -> str:
    return html.escape(state["items"][item_id])


def _btn_label(state: dict, item_id: int) -> str:
    name = state["items"][item_id]
    return name if len(name) <= 25 else name[:24] + "…"


def _keyboard(state: dict) -> InlineKeyboardMarkup:
    m = state["match"]
    nonce = state.get("nonce", 0)
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(f"🅰️ {_btn_label(state, m['a'])}",
                             callback_data=f"tny:{nonce}:{m['no']}:a"),
        InlineKeyboardButton(f"🅱️ {_btn_label(state, m['b'])}",
                             callback_data=f"tny:{nonce}:{m['no']}:b"),
    ]])


def _match_text(state: dict, banner: str = "") -> str:
    m = state["match"]
    lines = []
    if banner:
        lines += [banner, ""]
    lines += [
        f"🏆 <b>{html.escape(state['title'])}</b> — round {state['round']}, "
        f"match {m['no']} · {remaining(state)} left",
        "",
        f"🅰️ <b>{_name(state, m['a'])}</b>",
        "🆚",
        f"🅱️ <b>{_name(state, m['b'])}</b>",
        "",
        "Vote! The first two votes decide.",
    ]
    if m["votes"]:
        voted = ", ".join(html.escape(v[1]) for v in m["votes"].values())
        lines.append(f"✅ Voted so far: {voted}")
    return "\n".join(lines)


async def _post_match(chat_id, context, state, banner=""):
    await context.bot.send_message(
        chat_id, _match_text(state, banner),
        parse_mode=ParseMode.HTML, reply_markup=_keyboard(state),
    )


def _parse(raw: str) -> tuple[str, list[str]]:
    title = "Tournament"
    if ":" in raw.split(",")[0] and ":" in raw:
        title, raw = raw.split(":", 1)
        title = title.strip() or "Tournament"
    sep = "\n" if "\n" in raw else ","
    items = []
    for part in raw.split(sep):
        part = " ".join(part.split()).strip(" ,")
        if part and part.lower() not in (i.lower() for i in items):
            items.append(part[:60])
    return title[:60], items


async def tournament_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_group(update):
        return
    msg = update.effective_message
    chat_id = update.effective_chat.id
    raw = (msg.text or "").split(None, 1)[1] if len((msg.text or "").split(None, 1)) > 1 else ""
    state = db.get_tournament(chat_id)

    if raw.strip().lower() == "reset":
        db.clear_tournament(chat_id)
        await msg.reply_text("🗑 Tournament wiped. Start a new one: "
                             "/tournament Title: item, item, item")
        return

    if raw.strip():  # new tournament from a list
        if state and state.get("champion") is None:
            await msg.reply_html(
                f"⚠️ <b>{html.escape(state['title'])}</b> is still running "
                f"({remaining(state)} left). Finish it or /tournament reset first."
            )
            return
        title, items = _parse(raw)
        if len(items) < 2:
            await msg.reply_text(
                "I need at least 2 things to fight! "
                "/tournament Movie Night: Dune, Inception, Parasite"
            )
            return
        if len(items) > MAX_ITEMS:
            await msg.reply_text(f"Max {MAX_ITEMS} entries — trim the list a bit.")
            return
        state = new_bracket(range(len(items)))
        state["items"] = items
        state["title"] = title
        start_next_match(state)
        db.save_tournament(chat_id, state)
        await msg.reply_html(
            f"🏆 <b>{html.escape(title)}</b> — {len(items)} contenders enter a "
            f"knockout bracket. Two votes decide each matchup!"
        )
        await _post_match(chat_id, context, state)
        return

    if state is None:
        await msg.reply_text(
            "No tournament running. Start one:\n"
            "/tournament Movie Night: Dune, Inception, Parasite, Heat"
        )
        return
    if state["champion"] is not None:
        await msg.reply_html(
            f"🏆 <b>{html.escape(state['title'])}</b> champion: "
            f"<b>{_name(state, state['champion'])}</b>! /tournament reset to run it back."
        )
        return
    if state["match"]:
        await _post_match(chat_id, context, state, banner="⏳ Still open — votes needed!")
        return
    match, new_round = start_next_match(state)
    db.save_tournament(chat_id, state)
    if match is None:
        await context.bot.send_message(
            chat_id,
            f"🏆 The winner of <b>{html.escape(state['title'])}</b>: "
            f"✨ <b>{_name(state, state['champion'])}</b> ✨",
            parse_mode=ParseMode.HTML,
        )
        return
    banner = (f"🏁 <b>Round {state['round']}</b> — {remaining(state)} left!"
              if new_round else "")
    await _post_match(chat_id, context, state, banner)


async def vote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q.message is None:
        await q.answer()
        return
    chat_id = q.message.chat.id
    async with _locks[chat_id]:
        await _vote_locked(q, chat_id)


async def _vote_locked(q, chat_id: int):
    parts = q.data.split(":")
    if len(parts) == 4:
        nonce, match_no, choice = int(parts[1]), int(parts[2]), parts[3]
    else:  # buttons from before nonces existed
        nonce, match_no, choice = None, int(parts[1]), parts[2]
    state = db.get_tournament(chat_id)
    m = state["match"] if state else None
    if (not m or m["no"] != match_no
            or (nonce is not None and nonce != state.get("nonce", 0))):
        await q.answer("This matchup is already decided.")
        return

    uid = str(q.from_user.id)
    prev = m["votes"].get(uid)
    if prev and prev[0] == choice:
        await q.answer("That's already your vote.")
        return
    m["votes"][uid] = [choice, q.from_user.first_name]

    if len(m["votes"]) < 2:
        db.save_tournament(chat_id, state)
        await q.answer("Vote locked in — waiting for the second voter.")
        try:
            await q.edit_message_text(
                _match_text(state), parse_mode=ParseMode.HTML,
                reply_markup=_keyboard(state),
            )
        except TelegramError:
            pass
        return

    a_votes = sum(1 for v in m["votes"].values() if v[0] == "a")
    voters = " & ".join(html.escape(v[1]) for v in m["votes"].values())
    name_a, name_b = _name(state, m["a"]), _name(state, m["b"])
    is_final = not state["queue"] and not state["advancers"]
    state["match"] = None
    lines = []

    if a_votes != 1:  # 2-0
        winner = m["a"] if a_votes == 2 else m["b"]
        w_name = name_a if winner == m["a"] else name_b
        l_name = name_b if winner == m["a"] else name_a
        state["advancers"].append(winner)
        lines.append(f"✅ {voters} agree: <b>{w_name}</b> beats {l_name} 2–0!")
    elif not is_final:
        state["advancers"] += [m["a"], m["b"]]
        lines.append(f"🤝 1–1 — <b>{name_a}</b> and <b>{name_b}</b> both survive.")
    elif state["final_draws"] < 1:
        state["final_draws"] += 1
        state["queue"] = [m["a"], m["b"]]
        random.shuffle(state["queue"])
        lines.append(f"😱 1–1 in the FINAL! One rematch — /tournament when ready.")
    else:
        winner = random.choice([m["a"], m["b"]])
        state["advancers"].append(winner)
        w_name = name_a if winner == m["a"] else name_b
        lines.append(f"🪙 Deadlocked again — the coin says: <b>{w_name}</b>!")

    champion = not state["queue"] and len(state["advancers"]) == 1
    if champion:
        state["champion"] = state["advancers"].pop()
        lines.append(
            f"\n🏆 <b>{html.escape(state['title'])}</b> has a winner: "
            f"✨ <b>{_name(state, state['champion'])}</b> ✨"
        )
    elif not state["queue"] and state["advancers"]:
        lines.append(f"🏁 Round {state['round']} complete — "
                     f"{len(state['advancers'])} advance! /tournament for the next one.")
    elif not lines[-1].startswith("😱"):
        lines.append(f"{remaining(state)} left. /tournament for the next matchup.")

    db.save_tournament(chat_id, state)
    await q.answer()
    try:
        await q.edit_message_text("\n".join(lines), parse_mode=ParseMode.HTML)
    except TelegramError:
        pass


def get_handlers():
    return [
        CommandHandler("tournament", tournament_cmd),
        CallbackQueryHandler(vote, pattern=r"^tny:"),
    ]
