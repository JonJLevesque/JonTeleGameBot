"""/settle — the bot's supreme court rules on any argument, with prejudice.

Describe the dispute (/settle who should pick the movie tonight), or reply
to a message with /settle to enter it into evidence. AI-judged when a key
is configured; otherwise a dramatic coin flip between the two parties.
"""
import html
import random

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import CommandHandler, ContextTypes

import ai
import db
from .common import is_duo_chat, require_group

_FLIP = [
    "RULING: {w} is right. The court did not need to hear arguments; "
    "it simply knows. {l} is ordered to accept this with grace.",
    "RULING: judgment for {w}. The evidence was overwhelming, or at least "
    "the coin was. {l}, the court thanks you for your service as the wrong one.",
    "RULING: {w} wins on the merits. {l}'s argument was described by the "
    "clerk as 'brave'. Case closed.",
]


async def settle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_group(update):
        return
    msg = update.effective_message
    chat_id = update.effective_chat.id
    dispute = " ".join(context.args or [])
    if msg.reply_to_message and msg.reply_to_message.text:
        quoted = msg.reply_to_message.text[:400]
        who = msg.reply_to_message.from_user
        dispute += f"\n(Entered into evidence, from {who.first_name if who else 'unknown'}: “{quoted}”)"
    if not dispute.strip():
        await msg.reply_text(
            "State your case! /settle <the argument> — or reply to the "
            "offending message with /settle."
        )
        return

    verdict = None
    if ai.ENABLED:
        await context.bot.send_chat_action(chat_id, ChatAction.TYPING)
        verdict = await ai.generate(
            "settle", chat_id,
            duo=await is_duo_chat(update, context),
            spicy=db.is_spicy(chat_id),
            user_name=update.effective_user.first_name,
            extra=f"The dispute, as filed:\n{dispute}",
        )
    if not verdict:
        members = [m["first_name"] for m in db.chat_members(chat_id)][:2]
        while len(members) < 2:
            members.append("the other party")
        w, l = random.sample(members, 2)
        verdict = random.choice(_FLIP).format(w=w, l=l)

    await msg.reply_html(f"⚖️ <b>The court has ruled</b>\n\n{html.escape(verdict)}")


def get_handlers():
    return [CommandHandler("settle", settle)]
