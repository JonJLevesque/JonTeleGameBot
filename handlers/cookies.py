"""Cookie economy: /cookie, /cookies, /cookieboard."""
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

import db
from .common import require_group, target_from_message

MEDALS = ["🥇", "🥈", "🥉"]


async def give_cookie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_group(update):
        return
    giver = update.effective_user
    target_id, target_name = target_from_message(update, context)
    if target_id is None:
        await update.effective_message.reply_text(
            target_name or "Who gets the cookie? Reply to their message with /cookie, "
                           "or use /cookie @username."
        )
        return
    if target_id == giver.id:
        await update.effective_message.reply_text(
            "Nice try — you can't award yourself cookies. 🚫🍪"
        )
        return
    total = db.add_cookies(update.effective_chat.id, target_id, 1)
    await update.effective_message.reply_html(
        f"🍪 <b>{giver.first_name}</b> gave <b>{target_name}</b> a cookie! "
        f"They now have <b>{total}</b> cookie{'s' if total != 1 else ''}."
    )


async def show_cookies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_group(update):
        return
    target_id, target_name = target_from_message(update, context)
    if target_id is None:
        if target_name is not None:  # @username given but unknown
            await update.effective_message.reply_text(target_name)
            return
        target_id, target_name = update.effective_user.id, update.effective_user.first_name
    count = db.get_cookies(update.effective_chat.id, target_id)
    await update.effective_message.reply_html(
        f"🍪 <b>{target_name}</b> has <b>{count}</b> cookie{'s' if count != 1 else ''} in this chat."
    )


async def cookie_board(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_group(update):
        return
    top = db.cookie_leaderboard(update.effective_chat.id, limit=10)
    if not top:
        await update.effective_message.reply_text(
            "No cookies have been awarded here yet. Be the first: reply to someone with /cookie!"
        )
        return
    lines = ["🏆 <b>Cookie leaderboard</b>"]
    for rank, (name, count) in enumerate(top):
        medal = MEDALS[rank] if rank < len(MEDALS) else f"{rank + 1}."
        lines.append(f"{medal} {name} — {count} 🍪")
    await update.effective_message.reply_html("\n".join(lines))


def get_handlers():
    return [
        CommandHandler("cookie", give_cookie),
        CommandHandler("cookies", show_cookies),
        CommandHandler("cookieboard", cookie_board),
    ]
