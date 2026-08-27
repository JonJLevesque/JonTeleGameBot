"""/museum — the quote archive, curated. 🏛️

Every /quote is filed by the curator (AI) into a wing with a plaque; /museum
walks the wings, /museum <wing> tours one, /museum curate catalogues anything
still in storage.
"""
import html
import logging

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

import ai
import db
from .common import require_group
from .quotes import _nice_date

log = logging.getLogger("ajbot.museum")


async def curate(chat_id: int, quote_id: int) -> bool:
    row = db.quote_by_id(chat_id, quote_id)
    if row is None or row["wing"]:
        return False
    wings = [w for w, _ in db.museum_wings(chat_id) if w != "Uncatalogued"]
    result = await ai.curate_quote(row["text"], row["author_name"], wings)
    if not result:
        return False
    db.quote_set_curation(quote_id, *result)
    return True


def exhibit_text(r) -> str:
    plaque = f"\n<i>{html.escape(r['plaque'])}</i>" if r["plaque"] else ""
    return (f"“{html.escape(r['text'])}”\n— <b>{html.escape(r['author_name'])}</b>, "
            f"{_nice_date(r['ts'])}{plaque}")


async def museum_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_group(update):
        return
    msg = update.effective_message
    chat_id = update.effective_chat.id
    arg = " ".join(context.args or []).strip()
    if arg.lower() == "curate":
        rows = db.uncurated_quotes(chat_id)
        if not rows:
            await msg.reply_text("Everything is catalogued. The curator is having a coffee.")
            return
        await context.bot.send_chat_action(chat_id, "typing")
        n = sum([await curate(chat_id, r["id"]) for r in rows])
        await msg.reply_text(f"Catalogued {n} exhibit{'s' if n != 1 else ''}." if n else "The curator is unavailable (AI off?).")
        return
    wings = db.museum_wings(chat_id)
    if not wings:
        await msg.reply_text("The museum is empty. Reply to a legendary message with /quote to open the first wing.")
        return
    if arg:
        rows = db.museum_wing(chat_id, arg)
        if not rows:
            await msg.reply_html(f"No wing called <b>{html.escape(arg)}</b>. /museum lists them.")
            return
        lines = [f"🏛️ <b>{html.escape(rows[0]['wing'] or 'Uncatalogued')}</b> — {len(rows)} exhibit{'s' if len(rows) != 1 else ''}\n"]
        lines += [exhibit_text(r) for r in rows[:12]]
        if len(rows) > 12:
            lines.append(f"<i>…and {len(rows) - 12} more</i>")
        await msg.reply_html("\n\n".join(lines))
        return
    total = sum(n for _, n in wings)
    lines = [f"🏛️ <b>The Museum of {html.escape(update.effective_chat.title or 'Us')}</b> — {total} exhibit{'s' if total != 1 else ''}\n"]
    lines += [f"• <b>{html.escape(w)}</b> — {n}" for w, n in wings]
    feature = db.random_quote(chat_id)
    if feature and feature["wing"]:
        lines.append(f"\n<b>On display today</b> ({html.escape(feature['wing'])}):\n{exhibit_text(feature)}")
    lines.append("\n/museum &lt;wing&gt; to tour one · /quote (reply) to donate · /museum curate")
    await msg.reply_html("\n".join(lines))


def get_handlers():
    return [CommandHandler("museum", museum_cmd)]
