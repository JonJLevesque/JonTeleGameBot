"""/tldr, /settle, /hottake, /duck."""
import re

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import CommandHandler, ContextTypes

import ai
import db
from .common import arg_text

_URL = re.compile(r"https?://\S+")


async def _typing(update, context):
    await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)


async def tldr(update: Update, context: ContextTypes.DEFAULT_TYPE):
    m = _URL.search(arg_text(update))
    if not m:
        await update.effective_message.reply_text("Give me a link: /tldr https://… (or reply to one)")
        return
    await _typing(update, context)
    out = await ai.tldr(update.effective_chat.id, m.group(0))
    await update.effective_message.reply_text(out or "Couldn't get at that one.")


async def settle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = arg_text(update)
    if not text:
        await update.effective_message.reply_text("Usage: /settle tabs vs spaces (or reply to the argument)")
        return
    await _typing(update, context)
    out = await ai.freeform(
        update.effective_chat.id,
        "Settle this argument. Pick a side — no 'it depends', no both-sides. Give "
        "the ruling in one line, then the two or three strongest reasons, and one "
        "concession to the loser so they can live with it. Under 120 words.",
        f"The argument: {text}",
    )
    await update.effective_message.reply_text(out or "The court is in recess.")


async def hottake(update: Update, context: ContextTypes.DEFAULT_TYPE):
    topic = arg_text(update)
    await _typing(update, context)
    out = await ai.freeform(
        update.effective_chat.id,
        "Produce one hot take about software/tech to start a fight in this chat — "
        "a genuinely contestable opinion, stated with full confidence, one to two "
        "sentences, no hedging. Ideally about something these two actually use or "
        "argue about." + (f" Topic: {topic}." if topic else ""),
        effort="low",
    )
    await update.effective_message.reply_text(out or "🔥 Nothing. Even I have limits.")


async def duck(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id, uid = update.effective_chat.id, update.effective_user.id
    text = arg_text(update)
    if text.lower() == "stop":
        db.set_duck(chat_id, uid, None)
        await update.effective_message.reply_text("🦆 Session over. Did you find it?")
        return
    db.set_duck(chat_id, uid, "")
    await update.effective_message.reply_text(
        "🦆 Go. Explain the bug from the top. I'll only ask questions. /duck stop when done."
    )
    if text:
        await duck_turn(update, context, text)


async def duck_turn(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> bool:
    """Called by the listener for any message from a user with an open duck session."""
    chat_id, uid = update.effective_chat.id, update.effective_user.id
    transcript = db.get_duck(chat_id, uid)
    if transcript is None:
        return False
    await _typing(update, context)
    q = await ai.duck(transcript, text)
    if q:
        db.set_duck(chat_id, uid, f"{transcript}\nthem: {text}\nduck: {q}"[-6000:])
        await update.effective_message.reply_text("🦆 " + q)
    return True


def get_handlers():
    return [
        CommandHandler("tldr", tldr),
        CommandHandler("settle", settle),
        CommandHandler("hottake", hottake),
        CommandHandler("duck", duck),
    ]
