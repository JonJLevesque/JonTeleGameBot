"""Long-term recall: a nightly journal entry per chat and full-text search
over everything ever said. /yesterday and /recall expose them directly; the
persona gets both automatically in its context."""
import html
import logging
from datetime import datetime, time as dtime, timedelta

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

import ai
import db
from .common import LOCAL_TZ, arg_text

log = logging.getLogger("edgarjon.memory")


def day_bounds(day: str) -> tuple[float, float]:
    start = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=LOCAL_TZ)
    return start.timestamp(), (start + timedelta(days=1)).timestamp()


async def write_journal(chat_id: int, day: str, force=False) -> str | None:
    if not force and db.journal_get(chat_id, day):
        return db.journal_get(chat_id, day)["summary"]
    lo, hi = day_bounds(day)
    rows = db.messages_between(chat_id, lo, hi)
    if len(rows) < 3:
        return None
    summary = await ai.summarize_day(chat_id, day, rows) if ai.ENABLED else None
    if not summary:
        # Keyless fallback: who talked and the first few lines.
        names = sorted({r["name"] for r in rows})
        summary = f"{len(rows)} messages from {', '.join(names)}. Opened with: " + " / ".join(r["text"][:60] for r in rows[:3])
    db.journal_put(chat_id, day, summary, len(rows))
    return summary


async def journal_job(context: ContextTypes.DEFAULT_TYPE):
    """Nightly: journal yesterday (and any of the last 7 days that were missed)."""
    today = datetime.now(LOCAL_TZ).date()
    days = [(today - timedelta(days=i)).isoformat() for i in range(1, 8)]
    for chat_id in db.chat_ids_with_messages():
        for day in db.journal_missing_days(chat_id, days):
            try:
                await write_journal(chat_id, day)
            except Exception:
                log.exception("journal failed %s %s", chat_id, day)


async def yesterday_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    arg = arg_text(update).strip()
    if arg and arg[:4].isdigit():
        day = arg[:10]
    else:
        back = 1
        if arg.isdigit():
            back = int(arg)
        day = (datetime.now(LOCAL_TZ).date() - timedelta(days=back)).isoformat()
    await context.bot.send_chat_action(chat_id, "typing")
    summary = await write_journal(chat_id, day)
    if not summary:
        await update.effective_message.reply_text(f"Nothing much happened on {day}.")
        return
    await update.effective_message.reply_html(f"📓 <b>{day}</b>\n{html.escape(summary)}")


async def recall_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    q = arg_text(update)
    if not q:
        await update.effective_message.reply_text("/recall <words> — I'll dig through everything we've said.")
        return
    rows = db.search_messages(chat_id, q, limit=10, exclude_last=0)
    if not rows:
        await update.effective_message.reply_text("Nothing in the archive matches that.")
        return
    rows = sorted(rows, key=lambda r: r["id"])
    lines = [f"🔎 <b>{html.escape(q)}</b>"]
    for r in rows:
        d = datetime.fromtimestamp(r["ts"], LOCAL_TZ).strftime("%b %-d")
        lines.append(f"<i>{d}</i> <b>{html.escape(r['name'])}</b>: {html.escape(r['text'][:200])}")
    await update.effective_message.reply_html("\n".join(lines))


def schedule(app: Application):
    app.job_queue.run_daily(journal_job, dtime(3, 15, tzinfo=LOCAL_TZ), name="journal")
    app.job_queue.run_once(journal_job, 90, name="journal-catchup")


def get_handlers():
    return [
        CommandHandler("yesterday", yesterday_cmd),
        CommandHandler("recall", recall_cmd),
    ]
