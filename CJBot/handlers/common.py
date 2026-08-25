"""Helpers shared by the command handlers."""
import time
from datetime import datetime

from telegram import Update
from telegram.ext import ContextTypes

import db

GROUP_TYPES = ("group", "supergroup")


def _local_tz():
    """The host's real timezone (DST-aware). datetime.astimezone() alone
    yields a fixed offset frozen at process start, which would shift every
    daily job by an hour after a DST transition."""
    try:
        import os
        from zoneinfo import ZoneInfo
        path = os.path.realpath("/etc/localtime")
        if "zoneinfo/" in path:
            return ZoneInfo(path.split("zoneinfo/", 1)[1])
    except Exception:
        pass
    return datetime.now().astimezone().tzinfo


LOCAL_TZ = _local_tz()  # host timezone for all daily jobs

_member_counts: dict[int, tuple[int, float]] = {}  # chat_id -> (count, expiry)


async def is_duo_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """True for a group with exactly two humans (member count includes the
    bot). Cached for 5 minutes to avoid an API call on every prompt."""
    chat = update.effective_chat
    if chat.type not in GROUP_TYPES:
        return False
    cached = _member_counts.get(chat.id)
    now = time.monotonic()
    if cached and cached[1] > now:
        count = cached[0]
    else:
        count = await context.bot.get_chat_member_count(chat.id)
        _member_counts[chat.id] = (count, now + 300)
    return count <= 3


async def require_group(update: Update) -> bool:
    """True if the command was sent in a group; otherwise explain and bail."""
    if update.effective_chat.type in GROUP_TYPES:
        return True
    await update.effective_message.reply_text(
        "This command only works in group chats — add me to a group and try there!"
    )
    return False


async def is_chat_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    member = await context.bot.get_chat_member(
        update.effective_chat.id, update.effective_user.id
    )
    return member.status in ("administrator", "creator")


def target_from_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Resolve the user a command is aimed at.

    Checks, in order: the replied-to message's sender, then an @username
    argument (resolved from the chat-member cache, since the Bot API cannot
    look up usernames). Returns (user_id, first_name), or (None, error_text)
    when an @username was given but is unknown, or (None, None) if no target
    was specified at all.
    """
    msg = update.effective_message
    if msg.reply_to_message and msg.reply_to_message.from_user:
        u = msg.reply_to_message.from_user
        if u.is_bot:
            return None, "Bots can't be a target — pick a human."
        return u.id, u.first_name
    for arg in context.args or []:
        if arg.startswith("@"):
            found = db.resolve_username(update.effective_chat.id, arg)
            if found:
                return found
            return None, (
                f"I don't know {arg} yet — I only learn members when they talk. "
                "Reply to one of their messages instead."
            )
    return None, None


def track_users(update: Update) -> None:
    """Cache every user we can see so @username lookups and leaderboards work."""
    chat = update.effective_chat
    if chat is None or chat.type not in GROUP_TYPES:
        return
    msg = update.effective_message
    if update.effective_user:
        db.remember_user(chat.id, update.effective_user)
    if msg and msg.reply_to_message and msg.reply_to_message.from_user:
        db.remember_user(chat.id, msg.reply_to_message.from_user)
    if msg and msg.new_chat_members:
        for u in msg.new_chat_members:
            db.remember_user(chat.id, u)
