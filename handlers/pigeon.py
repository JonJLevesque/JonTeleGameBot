"""/tell — the carrier-pigeon service. 🕊️

DM the bot a message for someone in your group and it delivers it to their
DMs, word for word, without you having to say it to them directly. If their
DM with the bot isn't open yet, the whisper waits in their inbox and the
bot teases them in the group with a "you've got mail" button.
"""
import html
import random

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import TelegramError
from telegram.ext import CommandHandler, ContextTypes

import db

MAX_LEN = 3000  # leaves headroom under Telegram's 4096-char message limit

_TAGLINES = [
    "A little bird told me. I am the little bird.",
    "Delivered word for word, as sworn under pigeon oath.",
    "I flew all this way, the least you could do is read it.",
    "No take-backs — the pigeon has already landed.",
    "Contents faithfully transcribed. The pigeon reads nothing. (The pigeon reads everything.)",
]

USAGE = (
    "🕊️ <b>Carrier-pigeon service</b>\n\n"
    "Tell me something here in private and I'll deliver it for you:\n"
    "  <code>/tell Jon you were right about the movie</code>\n"
    "  <code>/tell @username miss you, dummy</code>\n\n"
    "I deliver it to their DMs, word for word. I can only reach people "
    "who've talked in a group we share."
)


def _delivery_text(sender_name: str, message: str) -> str:
    return (
        f"🕊️ <b>Special delivery!</b> {html.escape(sender_name)} asked me "
        f"to tell you something:\n\n"
        f"“{html.escape(message)}”\n\n"
        f"<i>{random.choice(_TAGLINES)}</i>"
    )


async def _try_deliver(context: ContextTypes.DEFAULT_TYPE, whisper) -> bool:
    """DM one whisper to its recipient. False if their DM is closed."""
    try:
        await context.bot.send_message(
            whisper["recipient_id"],
            _delivery_text(whisper["sender_name"], whisper["message"]),
            parse_mode="HTML",
        )
    except TelegramError:
        return False
    db.mark_whisper_delivered(whisper["id"])
    return True


async def flush_inbox(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> int:
    """Deliver any waiting whispers to a user who just opened a DM with the
    bot; each sender is told their message finally arrived. Returns how many
    were delivered. Called from /inbox, the deep link, and /start."""
    delivered = 0
    for w in db.pending_whispers(user_id):
        if not await _try_deliver(context, w):
            break  # DM still closed; the rest would fail too
        delivered += 1
        try:
            await context.bot.send_message(
                w["sender_id"],
                f"🕊️ Delivered! {w['recipient_name']} just picked up "
                f"your message.",
            )
        except TelegramError:
            pass  # sender's DM closed; they'll live
    return delivered


async def _tease_in_group(context: ContextTypes.DEFAULT_TYPE, whisper) -> bool:
    """Announce in a shared group that mail is waiting, with a button that
    deep-links into the bot's DM to collect it."""
    btn = InlineKeyboardMarkup([[InlineKeyboardButton(
        "📬 Collect your message",
        url=f"https://t.me/{context.bot.username}?start=inbox",
    )]])
    text = (
        f"📨 Psst, {html.escape(whisper['recipient_name'])} — "
        f"{html.escape(whisper['sender_name'])} left a private message "
        f"with me for you! Tap below and hit Start to collect it."
    )
    for chat_id in db.shared_chats(whisper["sender_id"], whisper["recipient_id"]):
        try:
            await context.bot.send_message(
                chat_id, text, parse_mode="HTML", reply_markup=btn
            )
            return True
        except TelegramError:
            continue
    return False


async def tell_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    sender = update.effective_user

    if update.effective_chat.type != "private":
        btn = InlineKeyboardMarkup([[InlineKeyboardButton(
            "🕊️ Whisper in my DMs",
            url=f"https://t.me/{context.bot.username}?start=tell",
        )]])
        await msg.reply_text(
            "🤫 Whispers are private! Tell me in my DMs and I'll "
            "deliver it for you.",
            reply_markup=btn,
        )
        return

    args = context.args or []
    if len(args) < 2:
        await msg.reply_html(USAGE)
        return

    token, message = args[0], " ".join(args[1:])
    if len(message) > MAX_LEN:
        await msg.reply_text(
            f"That's a whole novel ({len(message)} characters) — my wings "
            f"can carry {MAX_LEN}. Trim it down a bit?"
        )
        return

    own = (token.lstrip("@").lower() == (sender.username or "").lower()
           or token.lower() == sender.first_name.lower())
    candidates = db.resolve_recipient(sender.id, token)
    if not candidates:
        if own:
            await msg.reply_text(
                "Delivering a message to yourself? Done: you said "
                f"“{message}”. That'll be no charge."
            )
            return
        await msg.reply_html(
            f"I don't know <b>{html.escape(token)}</b> from any group we "
            f"share — I only learn people when they talk. Try their "
            f"@username, or have them send a message in the group first."
        )
        return
    if len(candidates) > 1:
        names = ", ".join(html.escape(n) for _, n in candidates)
        await msg.reply_html(
            f"I know more than one <b>{html.escape(token)}</b> ({names}) — "
            f"use their @username so I deliver to the right door."
        )
        return

    recipient_id, recipient_name = candidates[0]
    wid = db.create_whisper(
        sender.id, sender.first_name, recipient_id, recipient_name, message
    )
    whisper = {
        "id": wid, "sender_id": sender.id, "sender_name": sender.first_name,
        "recipient_id": recipient_id, "recipient_name": recipient_name,
        "message": message,
    }
    safe_name = html.escape(recipient_name)
    if await _try_deliver(context, whisper):
        await msg.reply_html(
            f"🕊️ Delivered to <b>{safe_name}</b>, word for word. "
            f"What happens next is between you two."
        )
    elif await _tease_in_group(context, whisper):
        await msg.reply_html(
            f"<b>{safe_name}</b> hasn't opened a DM with me yet, so I "
            f"couldn't knock directly — but I've left them a note in the "
            f"group (message contents sealed 🔏). It delivers the moment "
            f"they tap it."
        )
    else:
        await msg.reply_html(
            f"<b>{safe_name}</b> hasn't opened a DM with me yet, so it's "
            f"waiting in their inbox — it delivers as soon as they message "
            f"me or hit /start."
        )


async def inbox_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        await update.effective_message.reply_text(
            "📬 Your inbox is private — DM me /inbox to check it."
        )
        return
    n = await flush_inbox(context, update.effective_user.id)
    if n == 0:
        await update.effective_message.reply_text(
            "📭 No mail today. Someone can send you some with /tell!"
        )


async def inbox_from_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Deep-link entry: the recipient tapped the group's Collect button."""
    n = await flush_inbox(context, update.effective_user.id)
    if n == 0:
        await update.effective_message.reply_text(
            "📭 Looks like that message was already delivered — "
            "check just above!"
        )


async def tell_from_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Deep-link entry: someone tapped 'Whisper in my DMs' in the group."""
    await update.effective_message.reply_html(USAGE)


def get_handlers():
    return [
        CommandHandler("tell", tell_cmd),
        CommandHandler("inbox", inbox_cmd),
    ]
