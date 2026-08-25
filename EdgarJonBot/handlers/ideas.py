"""/idea, /ideas, /pick — the idea vault."""
import html
import random

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

import ai
import db
from .common import arg_text, fmt_when


async def idea(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    chat_id = update.effective_chat.id
    args = context.args or []
    if len(args) == 2 and args[0] in ("done", "rm") and args[1].isdigit():
        iid = int(args[1])
        ok = db.set_idea_done(chat_id, iid) if args[0] == "done" else db.delete_idea(chat_id, iid)
        await msg.reply_text(
            (f"#{iid} " + ("shipped. Finally." if args[0] == "done" else "gone."))
            if ok else f"No idea #{iid} here."
        )
        return
    text = arg_text(update)
    if not text:
        await msg.reply_text("Usage: /idea we should build a thing (or reply to a message with /idea)")
        return
    by = update.effective_user.first_name
    if msg.reply_to_message and msg.reply_to_message.from_user and not (msg.text or "").strip().count(" "):
        by = msg.reply_to_message.from_user.first_name
    iid = db.add_idea(chat_id, text, by, "command")
    await msg.reply_text(f"Filed as #{iid}. The vault does not forget.")


async def ideas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = db.ideas(update.effective_chat.id, limit=30)
    if not rows:
        await update.effective_message.reply_text("The vault is empty. Suspicious.")
        return
    lines = [
        f"<b>#{r['id']}</b> {html.escape(r['text'])} <i>— {html.escape(r['by_name'])}"
        f"{', overheard' if r['source'] == 'overheard' else ''}, {fmt_when(r['ts'])}</i>"
        for r in rows
    ]
    await update.effective_message.reply_html("💡 <b>Idea vault</b>\n" + "\n".join(lines))


async def pick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    rows = db.ideas(chat_id, limit=200)
    if not rows:
        await update.effective_message.reply_text("Nothing to pick from. /idea something first.")
        return
    r = random.choice(rows)
    line = f"💡 #{r['id']}: {r['text']}\n({r['by_name']}, {fmt_when(r['ts'])})"
    take = await ai.freeform(
        chat_id,
        "You're resurfacing an old idea from the vault. In one or two lines: is it "
        "still worth doing, given what's happened since? Be honest and a little "
        "provocative — the goal is to make them either build it or kill it.",
        f"The idea: {r['text']}", effort="low",
    )
    if take:
        line += "\n\n" + take
    await update.effective_message.reply_text(line)


def get_handlers():
    return [
        CommandHandler("idea", idea),
        CommandHandler("ideas", ideas),
        CommandHandler("pick", pick),
    ]
