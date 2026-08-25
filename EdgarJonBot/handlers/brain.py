"""/remember, /brain, /forget — the fact store."""
import html

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

import db
from .common import arg_text, fmt_when


async def remember(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = arg_text(update)
    if not text:
        await update.effective_message.reply_text("Usage: /remember Edgar's Postgres thing lives on branch wip/pg")
        return
    db.add_fact(update.effective_chat.id, text, "command")
    await update.effective_message.reply_text("Noted.")


async def brain(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = db.facts(update.effective_chat.id, limit=40)
    if not rows:
        await update.effective_message.reply_text("Empty. Talk more.")
        return
    lines = [f"<b>#{r['id']}</b> {html.escape(r['text'])} <i>({r['source']}, {fmt_when(r['ts'])})</i>"
             for r in rows]
    await update.effective_message.reply_html("🧠 <b>What I've got</b>\n" + "\n".join(lines))


async def forget(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args or []
    if not args or not args[0].isdigit():
        await update.effective_message.reply_text("Usage: /forget <id> (ids from /brain)")
        return
    ok = db.delete_fact(update.effective_chat.id, int(args[0]))
    await update.effective_message.reply_text("Forgotten." if ok else "No such fact.")


def get_handlers():
    return [
        CommandHandler("remember", remember),
        CommandHandler("brain", brain),
        CommandHandler("forget", forget),
    ]
