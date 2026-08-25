"""/shipped, /log, /recap and the Sunday recap job."""
import html
import logging
import time
from datetime import time as dtime

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

import ai
import db
from .common import LOCAL_TZ, arg_text, fmt_when

log = logging.getLogger("edgarjon.shipping")
WEEK = 7 * 86400


async def shipped(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = arg_text(update)
    if not text:
        await update.effective_message.reply_text("Usage: /shipped fixed the thing that was never broken")
        return
    u = update.effective_user
    db.add_shipped(update.effective_chat.id, u.id, u.first_name, text)
    await update.effective_message.reply_text(f"Logged. {u.first_name} ships.")


async def log_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = db.shipped_recent(update.effective_chat.id)
    if not rows:
        await update.effective_message.reply_text("Nothing shipped yet. Bold strategy.")
        return
    lines = [f"• <b>{html.escape(r['name'])}</b>: {html.escape(r['text'])} <i>({fmt_when(r['ts'])})</i>"
             for r in rows]
    await update.effective_message.reply_html("🚢 <b>Shipping log</b>\n" + "\n".join(lines))


async def build_recap(chat_id) -> str | None:
    since = time.time() - WEEK
    ships = db.shipped_since(chat_id, since)
    new_ideas = [r for r in db.ideas(chat_id, include_done=True, limit=200) if r["ts"] >= since]
    msgs = db.messages_since(chat_id, since)
    if not (ships or new_ideas or msgs):
        return None
    facts = "\n".join(
        [f"shipped by {r['name']}: {r['text']}" for r in ships]
        + [f"new idea ({r['source']}, {r['by_name']}): {r['text']}" for r in new_ideas]
    ) or "(nothing logged)"
    sample = "\n".join(f"{r['name']}: {r['text']}" for r in msgs[-120:]) or "(quiet week)"
    stale = [r for r in db.ideas(chat_id, limit=200) if time.time() - r["ts"] > 3 * WEEK]
    stale_txt = "\n".join(f"#{r['id']} {r['text']}" for r in stale[:5])
    text = await ai.freeform(
        chat_id,
        "Write the weekly recap for the chat. Plain text, under 200 words. Cover: "
        "what each of them shipped (by name, with a verdict on who out-shipped whom), "
        "the ideas that came up, one theme from the week's conversation, and — if "
        "any — one stale idea you'd like them to either build or kill. Dry, specific, "
        "affectionate. No headers, no bullet essay; short paragraphs.",
        f"This week's log:\n{facts}\n\nStale ideas (3+ weeks old):\n{stale_txt or '(none)'}"
        f"\n\nThe week's chat, for flavor:\n{sample}",
        effort="medium",
    )
    return text


async def recap(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = await build_recap(update.effective_chat.id)
    await update.effective_message.reply_text(text or "Nothing happened this week. I checked twice.")


async def _weekly(context: ContextTypes.DEFAULT_TYPE):
    seen = {r[0] for r in db.chats_with_unprocessed(0)}
    seen |= {r["chat_id"] for r in db._db().execute("SELECT DISTINCT chat_id FROM messages")}
    for chat_id in seen:
        try:
            text = await build_recap(chat_id)
            if text:
                await context.bot.send_message(chat_id, "📋 Week in review\n\n" + text)
        except Exception:
            log.exception("weekly recap failed for %s", chat_id)


def schedule(app: Application):
    app.job_queue.run_daily(_weekly, dtime(18, 0, tzinfo=LOCAL_TZ), days=(6,), name="weekly-recap")


def get_handlers():
    return [
        CommandHandler("shipped", shipped),
        CommandHandler("log", log_cmd),
        CommandHandler("recap", recap),
    ]
