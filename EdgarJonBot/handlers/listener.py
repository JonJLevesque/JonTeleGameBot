"""The always-on ear: logs every message, replies when addressed (or feels
like it), and periodically distills the conversation into ideas and facts."""
import logging
import random
import re
import time

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import Application, ContextTypes, MessageHandler, filters

import ai
import config
import db
from . import tools

log = logging.getLogger("edgarjon.listener")
_NAME_WORDS = [w for w in re.split(r"\W+", config.BOT_NAME.lower()) if len(w) > 2]


def _addressed(update: Update, bot_username: str) -> bool:
    msg = update.effective_message
    if update.effective_chat.type == "private":
        return True
    if msg.reply_to_message and msg.reply_to_message.from_user and \
            msg.reply_to_message.from_user.username == bot_username:
        return True
    text = (msg.text or "").lower()
    if f"@{bot_username.lower()}" in text:
        return True
    return any(re.search(rf"\b{re.escape(w)}\b", text) for w in _NAME_WORDS)


async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    user = update.effective_user
    if not msg or not user or user.is_bot or not msg.text:
        return
    chat_id = update.effective_chat.id
    db.remember_user(chat_id, user)
    pending = db.log_message(chat_id, user.id, user.first_name, msg.text)

    if await tools.duck_turn(update, context, msg.text):
        return

    addressed = _addressed(update, context.bot.username)
    if addressed or random.random() < config.CHIME_IN_RATE:
        await context.bot.send_chat_action(chat_id, ChatAction.TYPING)
        text = await ai.reply(chat_id, user_name=user.first_name, text=msg.text,
                              unprompted=not addressed)
        if text:
            await msg.reply_text(text)
        elif addressed:
            await msg.reply_text("…brain's offline. Try again in a minute.")

    if pending >= config.EXTRACT_EVERY:
        await distill(chat_id)


async def distill(chat_id: int):
    rows = db.unprocessed_messages(chat_id)
    if not rows:
        return
    result = await ai.extract(chat_id, rows)
    if result is None:
        return  # leave unprocessed; retried on the next trigger
    db.mark_processed([r["id"] for r in rows])
    by = ", ".join(sorted({r["name"] for r in rows}))
    for idea in result.get("ideas", []):
        db.add_idea(chat_id, idea, by, "overheard")
    for fact in result.get("facts", []):
        db.add_fact(chat_id, fact, "overheard")
    if result.get("ideas") or result.get("facts"):
        log.info("distilled chat %s: %d ideas, %d facts", chat_id,
                 len(result["ideas"]), len(result["facts"]))


async def _idle_sweep(context: ContextTypes.DEFAULT_TYPE):
    cutoff = time.time() - config.EXTRACT_IDLE_MINUTES * 60
    for chat_id, last_ts in db.chats_with_unprocessed(3):
        if last_ts < cutoff:
            try:
                await distill(chat_id)
            except Exception:
                log.exception("idle distill failed for %s", chat_id)


def schedule(app: Application):
    app.job_queue.run_repeating(_idle_sweep, interval=300, first=60, name="idle-distill")


def get_handlers():
    return [MessageHandler(filters.TEXT & ~filters.COMMAND, on_message)]
