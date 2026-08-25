"""/reminder — natural-language reminders, persisted and restored on restart."""
import html
import logging
import re
import time
from datetime import datetime, timedelta

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

import ai
import db
from .common import LOCAL_TZ, arg_text, fmt_when

log = logging.getLogger("edgarjon.reminders")

_REL = re.compile(r"^in\s+(\d+)\s*(m|min|mins|minutes?|h|hr|hrs|hours?|d|days?)\b\s*(.*)$", re.I)
_UNITS = {"m": 60, "h": 3600, "d": 86400}


def _quick_parse(text: str) -> tuple[float, str] | None:
    """Zero-latency path for 'in N units <text>'. Everything else goes to Claude."""
    m = _REL.match(text.strip())
    if not m:
        return None
    n, unit, rest = int(m.group(1)), m.group(2)[0].lower(), m.group(3).strip()
    if not rest:
        return None
    return time.time() + n * _UNITS[unit], rest


def _schedule(app: Application, rid: int, due: float):
    delay = max(0.0, due - time.time())
    app.job_queue.run_once(_fire, delay, data=rid, name=f"reminder-{rid}")


async def _fire(context: ContextTypes.DEFAULT_TYPE):
    r = db.get_reminder(context.job.data)
    if not r or r["fired"]:
        return
    db.mark_fired(r["id"])
    await context.bot.send_message(
        r["chat_id"], f"⏰ {r['name']}: {r['text']}"
    )


async def reminder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    chat_id = update.effective_chat.id
    args = context.args or []
    if len(args) == 2 and args[0] == "cancel" and args[1].isdigit():
        rid = int(args[1])
        if db.cancel_reminder(chat_id, rid):
            for j in context.application.job_queue.get_jobs_by_name(f"reminder-{rid}"):
                j.schedule_removal()
            await msg.reply_text(f"Reminder #{rid} cancelled.")
        else:
            await msg.reply_text(f"No pending reminder #{rid}.")
        return
    text = arg_text(update)
    if not text:
        await msg.reply_text("Usage: /reminder in 2h push the fix · /reminder friday 4pm demo to Edgar")
        return
    parsed = _quick_parse(text)
    if parsed:
        due, body = parsed
    else:
        p = await ai.parse_reminder(text)
        if not p or not p.get("due_iso"):
            await msg.reply_text("I couldn't find a time in that. Try 'in 30m …' or 'tomorrow 9am …'.")
            return
        try:
            due = datetime.fromisoformat(p["due_iso"]).timestamp()
        except ValueError:
            await msg.reply_text("Got a time I couldn't make sense of. Try again with something plainer.")
            return
        body = p.get("text") or text
    if due < time.time() + 5:
        await msg.reply_text("That's in the past. I'm good, but not that good.")
        return
    u = update.effective_user
    rid = db.add_reminder(chat_id, u.id, u.first_name, body, due)
    _schedule(context.application, rid, due)
    await msg.reply_text(f"#{rid} — {fmt_when(due)}: {body}")


async def reminders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = db.pending_reminders(update.effective_chat.id)
    if not rows:
        await update.effective_message.reply_text("No pending reminders.")
        return
    lines = [f"<b>#{r['id']}</b> {fmt_when(r['due'])} — {html.escape(r['text'])} <i>({html.escape(r['name'])})</i>"
             for r in rows]
    await update.effective_message.reply_html("⏰ <b>Pending</b>\n" + "\n".join(lines))


def restore(app: Application):
    n = 0
    for r in db.pending_reminders():
        _schedule(app, r["id"], r["due"])
        n += 1
    log.info("restored %d reminders", n)


def get_handlers():
    return [
        CommandHandler(["reminder", "remind", "remindme"], reminder),
        CommandHandler("reminders", reminders),
    ]
