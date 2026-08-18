"""Weekly recap: /recap on|now|off — a Sunday-evening scoreboard.

One global job fires daily at 19:00 local and posts to every enrolled chat
on Sundays: the week's Wordle duels and streaks, cookie movement, Beautiful
Place bracket progress, board games played, and the daily-question count.
"""
import html
import logging
from datetime import date, datetime, time, timedelta, timezone

from telegram import Update
from telegram.error import TelegramError
from telegram.ext import Application, CommandHandler, ContextTypes

import db
from .common import LOCAL_TZ, require_group
from .beautiful import _remaining as beautiful_remaining
from .wordle import _streak as wordle_streak

log = logging.getLogger("partybot.recap")

POST_AT = time(19, 0)


def _build(chat_id: int) -> str:
    since_day = (date.today() - timedelta(days=7)).isoformat()
    since_ts = (datetime.now(timezone.utc) - timedelta(days=7)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    members = {m["user_id"]: m["first_name"] for m in db.chat_members(chat_id)}
    lines = ["📊 <b>Weekly recap</b>"]

    wordle_lines = []
    for uid, name in members.items():
        plays = [p for p in db.wordle_user_days(uid) if p[0] >= since_day]
        if not plays:
            continue
        wins = db.wordle_duel_wins_since(chat_id, uid, since_day)
        solved = [n for _, won, n in plays if won]
        avg = f"{sum(solved) / len(solved):.1f}" if solved else "–"
        wordle_lines.append(
            f"  {html.escape(name)}: {len(plays)} played · {wins} duel "
            f"win{'s' if wins != 1 else ''} · avg {avg} · "
            f"streak {wordle_streak(uid)}"
        )
    if wordle_lines:
        lines.append("\n🟩 <b>Wordle</b>")
        lines += wordle_lines

    deltas = [(uid, d) for uid, d in db.cookie_deltas_since(chat_id, since_ts)
              if uid in members and d]
    if deltas:
        lines.append("\n🍪 <b>Cookie movement</b>")
        for uid, d in deltas:
            total = db.get_cookies(chat_id, uid)
            lines.append(
                f"  {html.escape(members[uid])}: {'+' if d > 0 else ''}{d} "
                f"this week (now {total})"
            )

    state = db.get_beautiful(chat_id)
    if state and state.get("champion") is None:
        played = state["match_no"] - (db.recap_snapshot(chat_id) or 0)
        lines.append(
            f"\n🌍 <b>Most Beautiful Place</b>: {played} matchup"
            f"{'s' if played != 1 else ''} this week — round {state['round']}, "
            f"{beautiful_remaining(state)} of {state['total']} places left"
        )
        db.recap_update_snapshot(chat_id, state["match_no"])

    games = db.finished_games_since(chat_id, since_ts)
    if games:
        lines.append(f"\n🎮 Board games finished this week: {games}")

    dq = db.dailyq_get(chat_id)
    if dq:
        lines.append(f"💬 Daily questions asked so far: {dq['idx']}")

    if len(lines) == 1:
        lines.append("A quiet week… someone start something. 👀")
    return "\n".join(lines)


async def _job(context: ContextTypes.DEFAULT_TYPE):
    if datetime.now(LOCAL_TZ).weekday() != 6:  # Sundays only
        return
    for chat_id in db.recap_all():
        try:
            await context.bot.send_message(
                chat_id, _build(chat_id), parse_mode="HTML"
            )
        except TelegramError:
            log.exception("recap failed for chat %s", chat_id)


def schedule(app: Application) -> None:
    app.job_queue.run_daily(
        _job, POST_AT.replace(tzinfo=LOCAL_TZ), name="weekly-recap"
    )


async def recap_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_group(update):
        return
    msg = update.effective_message
    chat_id = update.effective_chat.id
    arg = context.args[0].lower() if context.args else ""
    if arg == "on":
        db.recap_on(chat_id)
        await msg.reply_text(
            "📊 Weekly recap is on — every Sunday at "
            f"{POST_AT.strftime('%H:%M')}. (/recap now for a preview.)"
        )
    elif arg == "off":
        db.recap_off(chat_id)
        await msg.reply_text("📊 Weekly recap turned off.")
    elif arg == "now":
        db.recap_on(chat_id)
        await msg.reply_html(_build(chat_id))
    else:
        enrolled = chat_id in db.recap_all()
        await msg.reply_text(
            f"📊 Weekly recap is {'ON — Sundays at ' + POST_AT.strftime('%H:%M') if enrolled else 'off'}.\n"
            "/recap on | now | off"
        )


def get_handlers():
    return [CommandHandler("recap", recap_cmd)]
