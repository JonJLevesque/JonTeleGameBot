"""World's Most Beautiful Place: /beautiful — a photo-knockout tournament.

~2000 famous places (places.json, built by scripts/fetch_places.py) enter a
single-elimination bracket per chat. Each /beautiful summons one head-to-head:
two photos with 🅰️/🅱️ vote buttons. A matchup waits — indefinitely — until two
different people have voted:

  2-0 -> winner advances to the next round
  1-1 -> both survive and get new opponents next round; if it happens in the
         all-deciding final, one rematch, and after a second draw a coin flip

State lives in SQLite, so the bracket can idle for weeks between matchups.
"""
import asyncio
import html
import json
import random
from collections import defaultdict
from pathlib import Path

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    LinkPreviewOptions,
    Update,
)
from telegram.constants import ParseMode
from telegram.error import TelegramError
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

import db
from .common import require_group

_PLACES: list[dict] | None = None
_locks: dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)  # per-chat vote lock


def places() -> list[dict]:
    global _PLACES
    if _PLACES is None:
        path = Path(__file__).resolve().parent.parent / "places.json"
        _PLACES = json.loads(path.read_text()) if path.exists() else []
    return _PLACES


def _label(p: dict) -> str:
    return f"{p['name']} ({p['country']})" if p["country"] else p["name"]


def _esc_label(pid: int) -> str:
    return html.escape(_label(places()[pid]))


# ------------------------------------------------------------ bracket logic
# The generic engine lives in bracket.py (shared with /tournament); state
# shape is unchanged, so live tournaments survive this refactor.

from .bracket import new_bracket, remaining as _remaining, start_next_match as _start_next_match


def _new_state() -> dict:
    return new_bracket(range(len(places())))


# -------------------------------------------------------------- presentation

def _keyboard(state: dict) -> InlineKeyboardMarkup:
    match = state["match"]
    nonce = state.get("nonce", 0)  # 0 = bracket predating nonces

    def btn(side: str, pid: int) -> InlineKeyboardButton:
        name = places()[pid]["name"]
        name = name if len(name) <= 22 else name[:21] + "…"
        icon = "🅰️" if side == "a" else "🅱️"
        return InlineKeyboardButton(
            f"{icon} {name}", callback_data=f"wmbp:{nonce}:{match['no']}:{side}"
        )

    return InlineKeyboardMarkup([[btn("a", match["a"]), btn("b", match["b"])]])


def _parse_vote(data: str) -> tuple[int | None, int, str]:
    """(nonce, match_no, choice); nonce None for pre-nonce legacy buttons."""
    parts = data.split(":")
    if len(parts) == 4:
        return int(parts[1]), int(parts[2]), parts[3]
    return None, int(parts[1]), parts[2]


def _match_text(state: dict, banner: str = "") -> str:
    m = state["match"]
    pa, pb = places()[m["a"]], places()[m["b"]]
    lines = []
    if banner:
        lines += [banner, ""]
    lines += [
        f"🌍 <b>Most Beautiful Place</b> — round {state['round']}, "
        f"match {m['no']} · {_remaining(state)} places left",
        "",
        f"🅰️ <a href=\"{html.escape(pa['img'])}\">{_esc_label(m['a'])}</a>",
        "🆚",
        f"🅱️ <a href=\"{html.escape(pb['img'])}\">{_esc_label(m['b'])}</a>",
        "",
        "Which is more beautiful? The first two votes decide — both of you vote!",
    ]
    if m["votes"]:
        voted = ", ".join(html.escape(v[1]) for v in m["votes"].values())
        lines.append(f"✅ Voted so far: {voted}")
    return "\n".join(lines)


async def _post_match(chat_id: int, context: ContextTypes.DEFAULT_TYPE,
                      state: dict, banner: str = "") -> None:
    m = state["match"]
    pa, pb = places()[m["a"]], places()[m["b"]]
    album_ok = True
    try:
        await context.bot.send_media_group(
            chat_id,
            [
                InputMediaPhoto(pa["img"], caption=f"🅰️ {_label(pa)}"),
                InputMediaPhoto(pb["img"], caption=f"🅱️ {_label(pb)}"),
            ],
        )
    except TelegramError:
        album_ok = False  # rare bad URL: the vote message links both photos
    await context.bot.send_message(
        chat_id,
        _match_text(state, banner),
        parse_mode=ParseMode.HTML,
        reply_markup=_keyboard(state),
        link_preview_options=LinkPreviewOptions(is_disabled=album_ok),
    )


async def _announce_champion(chat_id: int, context: ContextTypes.DEFAULT_TYPE,
                             state: dict) -> None:
    p = places()[state["champion"]]
    caption = (
        f"🏆🌍 After {state['match_no']} matches across {state['round']} rounds, "
        f"the World's Most Beautiful Place is:\n\n"
        f"✨ {_label(p)} ✨\n\n"
        f"({state['total']} places entered. /beautiful reset to run it back.)"
    )
    try:
        await context.bot.send_photo(chat_id, p["img"], caption=caption)
    except TelegramError:
        await context.bot.send_message(chat_id, caption + f"\n{p['img']}")


# ------------------------------------------------------------------ handlers

async def beautiful(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_group(update):
        return
    msg = update.effective_message
    if len(places()) < 2:
        await msg.reply_text(
            "The photo pool is missing — run scripts/fetch_places.py first."
        )
        return
    chat_id = update.effective_chat.id
    arg = context.args[0].lower() if context.args else ""
    state = db.get_beautiful(chat_id)

    if arg == "reset":
        db.clear_beautiful(chat_id)
        await msg.reply_text(
            "🗑 Tournament wiped. Send /beautiful to start a fresh bracket."
        )
        return

    if arg in ("status", "stats"):
        if state is None:
            await msg.reply_text("No tournament yet — /beautiful starts one!")
        elif state["champion"] is not None:
            await msg.reply_html(
                f"🏆 Champion already crowned: <b>{_esc_label(state['champion'])}</b> "
                f"after {state['match_no']} matches. /beautiful reset to run it back."
            )
        else:
            waiting = ""
            if state["match"]:
                m = state["match"]
                waiting = (
                    f"\nCurrent matchup: {_esc_label(m['a'])} 🆚 {_esc_label(m['b'])} "
                    f"({len(m['votes'])}/2 votes in)"
                )
            await msg.reply_html(
                f"🌍 <b>Most Beautiful Place</b> — round {state['round']}, "
                f"{state['match_no']} matches played, "
                f"{_remaining(state)} of {state['total']} places remain.{waiting}\n"
                f"/beautiful shows the matchup."
            )
        return

    if state is None:
        state = _new_state()
        match, _ = _start_next_match(state)
        db.save_beautiful(chat_id, state)
        await msg.reply_html(
            f"🌍 <b>The World's Most Beautiful Place</b> 🌍\n"
            f"{state['total']} places from all over the planet enter a knockout "
            f"bracket. Each matchup: two photos, you both vote.\n"
            f"2–0 advances a place, 1–1 lets both live to fight again.\n"
            f"Last place standing wins the world. Here we go!"
        )
        await _post_match(chat_id, context, state)
        return

    if state["champion"] is not None:
        await msg.reply_html(
            f"🏆 This chat already crowned <b>{_esc_label(state['champion'])}</b>! "
            f"/beautiful reset to run it back."
        )
        return

    if state["match"]:  # still waiting on votes: re-post the matchup
        await _post_match(chat_id, context, state, banner="⏳ Still open — votes needed!")
        return

    match, new_round = _start_next_match(state)
    db.save_beautiful(chat_id, state)
    if match is None:  # only possible if a champion slipped through byes
        await _announce_champion(chat_id, context, state)
        return
    banner = (
        f"🏁 <b>Round {state['round']}</b> begins — "
        f"{_remaining(state)} places remain!" if new_round else ""
    )
    await _post_match(chat_id, context, state, banner)


async def vote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q.message is None:
        await q.answer()
        return
    chat_id = q.message.chat.id
    async with _locks[chat_id]:
        await _vote_locked(q, context, chat_id)


async def _vote_locked(q, context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    nonce, match_no, choice = _parse_vote(q.data)
    state = db.get_beautiful(chat_id)
    m = state["match"] if state else None
    if (not m or m["no"] != match_no
            or (nonce is not None and nonce != state.get("nonce", 0))):
        await q.answer("This matchup is already decided.")
        return

    uid = str(q.from_user.id)
    prev = m["votes"].get(uid)
    if prev and prev[0] == choice:
        await q.answer("That's already your vote — waiting on the other voter.")
        return
    m["votes"][uid] = [choice, q.from_user.first_name]

    if len(m["votes"]) < 2:
        db.save_beautiful(chat_id, state)
        await q.answer("Vote locked in — waiting for the second voter.")
        try:
            await q.edit_message_text(
                _match_text(state),
                parse_mode=ParseMode.HTML,
                reply_markup=_keyboard(state),
                link_preview_options=LinkPreviewOptions(is_disabled=True),
            )
        except TelegramError:
            pass
        return

    # Two distinct voters: resolve the matchup.
    a_votes = sum(1 for v in m["votes"].values() if v[0] == "a")
    voters = " & ".join(html.escape(v[1]) for v in m["votes"].values())
    name_a, name_b = _esc_label(m["a"]), _esc_label(m["b"])
    is_final = not state["queue"] and not state["advancers"]
    state["match"] = None
    lines = []

    if a_votes != 1:  # 2-0
        winner, loser = (m["a"], m["b"]) if a_votes == 2 else (m["b"], m["a"])
        w_name = name_a if winner == m["a"] else name_b
        l_name = name_b if winner == m["a"] else name_a
        state["advancers"].append(winner)
        lines.append(f"✅ {voters} agree: <b>{w_name}</b> beats {l_name} 2–0!")
    elif not is_final:
        state["advancers"] += [m["a"], m["b"]]
        lines.append(
            f"🤝 {voters} split it 1–1 — <b>{name_a}</b> and <b>{name_b}</b> "
            f"both survive and will face new challengers next round."
        )
    elif state["final_draws"] < 1:  # first draw in the final: rematch
        state["final_draws"] += 1
        state["queue"] = [m["a"], m["b"]]
        random.shuffle(state["queue"])
        lines.append(
            f"😱 1–1 in the <b>FINAL</b> between {name_a} and {name_b}! "
            f"One rematch to settle the world — /beautiful when you're ready."
        )
    else:  # second final draw: the coin decides
        winner = random.choice([m["a"], m["b"]])
        state["advancers"].append(winner)
        w_name = name_a if winner == m["a"] else name_b
        lines.append(f"🪙 Deadlocked again — the coin has spoken: <b>{w_name}</b>!")

    champion = not state["queue"] and len(state["advancers"]) == 1
    if champion:
        state["champion"] = state["advancers"].pop()
    elif not state["queue"]:
        lines.append(
            f"🏁 Round {state['round']} complete — {len(state['advancers'])} "
            f"places advance!"
        )
        lines.append("Send /beautiful for the next matchup.")
    elif state["match"] is None and not lines[-1].startswith("😱"):
        lines.append(
            f"{_remaining(state)} places left. Send /beautiful for the next matchup."
        )

    db.save_beautiful(chat_id, state)
    await q.answer()
    try:
        await q.edit_message_text(
            "\n".join(lines), parse_mode=ParseMode.HTML,
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )
    except TelegramError:
        pass
    if champion:
        await _announce_champion(chat_id, context, state)


def get_handlers():
    return [
        CommandHandler("beautiful", beautiful),
        CallbackQueryHandler(vote, pattern=r"^wmbp:"),
    ]
