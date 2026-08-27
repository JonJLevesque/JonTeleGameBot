"""/quote and /memory — the quote wall. 📜

Reply to a legendary message with /quote and it's preserved forever;
/memory resurfaces a random one from the archives (optionally filtered:
/memory pizza). The weekly recap features a memory of the week.
"""
import html

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

import db
from .common import require_group


def _nice_date(ts: str) -> str:
    """'2026-08-20 14:03:11' -> 'Aug 20, 2026' (best effort)."""
    try:
        from datetime import datetime
        return datetime.strptime(ts[:10], "%Y-%m-%d").strftime("%b %-d, %Y")
    except ValueError:
        return ts[:10]


async def quote_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_group(update):
        return
    msg = update.effective_message
    target = msg.reply_to_message
    if target is None:
        await msg.reply_text(
            "Reply to the legendary message with /quote and I'll preserve "
            "it for posterity."
        )
        return
    text = target.text or target.caption
    if not text:
        await msg.reply_text(
            "That message has no words to preserve — I archive text, "
            "not vibes."
        )
        return
    author = target.from_user
    author_name = author.first_name if author else "someone"
    saver = update.effective_user
    saved = db.save_quote(
        update.effective_chat.id, target.message_id,
        author.id if author else None, author_name,
        text, saver.id, saver.first_name,
    )
    if saved is None:
        await msg.reply_text("Already in the archive — a true classic. 📜")
        return
    n = db.quote_count(update.effective_chat.id)
    from . import museum
    curated = await museum.curate(update.effective_chat.id, saved)
    row = db.quote_by_id(update.effective_chat.id, saved)
    if curated and row and row["wing"]:
        await msg.reply_html(
            f"🏛️ Accessioned into the <b>{html.escape(row['wing'])}</b> wing as exhibit #{n}.\n"
            f"<i>{html.escape(row['plaque'] or '')}</i>"
        )
    else:
        await msg.reply_html(
            f"📌 Preserved for posterity — quote #{n} in the archive. "
            f"(/museum to browse, /memory for a random one.)"
        )


async def memory_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_group(update):
        return
    msg = update.effective_message
    term = " ".join(context.args or []).strip() or None
    row = db.random_quote(update.effective_chat.id, like=term)
    if row is None:
        if term:
            await msg.reply_html(
                f"Nothing in the archives about "
                f"<b>{html.escape(term)}</b> — yet."
            )
        else:
            await msg.reply_text(
                "The archive is empty — reply to a legendary message with "
                "/quote to start it."
            )
        return
    await msg.reply_html(
        f"📜 <b>From the archives</b>\n\n"
        f"“{html.escape(row['text'])}”\n"
        f"— <b>{html.escape(row['author_name'])}</b>, {_nice_date(row['ts'])}\n"
        f"<i>(preserved by {html.escape(row['saved_by_name'])})</i>"
    )


def get_handlers():
    return [
        CommandHandler("quote", quote_cmd),
        CommandHandler("memory", memory_cmd),
    ]
