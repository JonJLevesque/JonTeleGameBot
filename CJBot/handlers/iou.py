"""IOU tracker: who owes whom what, until it's paid. 🧾

Two ways a debt gets on the books: redeeming a shop reward (the reward's
owner owes the buyer), or writing one down by hand — /iou @cherry a back
rub (they owe you) or /iou owe @cherry dinner (you owe them). Either party
can mark it paid; the creditor can cancel; anyone can nudge, but each debt
only takes a nudge every few hours because the bot is a bookkeeper, not a
bailiff.
"""
import html
import random
import time as _time

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

import db
from .common import require_group, target_from_message

NUDGE_COOLDOWN = 6 * 3600

_NUDGES = [
    "{debtor}, the ledger says you owe {creditor} <b>{text}</b>. The ledger is patient. {creditor} is not.",
    "Gentle reminder for {debtor}: <b>{text}</b> for {creditor} remains outstanding. Interest is compounding emotionally.",
    "{debtor}! Re: <b>{text}</b> (owed to {creditor}). This is not a threat. It is a recap of a threat.",
    "The court notes {debtor} still owes {creditor} <b>{text}</b>, and that {creditor} has been very brave about it.",
]
_PAID = [
    "🧾 Debt cleared: {debtor} delivered <b>{text}</b> to {creditor}. Honor intact.",
    "🧾 <b>{text}</b> — paid in full by {debtor}. {creditor} can stop mentioning it now.",
    "🧾 {debtor} has settled <b>{text}</b>. The ledger closes with a satisfying thump.",
]


def age_text(created_at: float, now: float) -> str:
    days = int((now - created_at) // 86400)
    if days == 0:
        return "today"
    if days == 1:
        return "1 day"
    if days < 30:
        return f"{days} days"
    return f"{days // 30} mo"


def ledger_text(rows, now: float) -> str:
    if not rows:
        return "🧾 No open IOUs. Everyone is even, which is suspicious."
    by_debtor: dict[str, list] = {}
    for r in rows:
        by_debtor.setdefault(r["debtor_name"], []).append(r)
    lines = ["🧾 <b>Open IOUs</b>"]
    for debtor, items in by_debtor.items():
        lines.append(f"\n<b>{html.escape(debtor)}</b> owes:")
        for r in items:
            stale = " ⏳" if now - r["created_at"] > 14 * 86400 else ""
            lines.append(
                f"  #{r['id']} {html.escape(r['text'])} → "
                f"{html.escape(r['creditor_name'])} <i>({age_text(r['created_at'], now)})</i>{stale}"
            )
    lines.append("\n/iou paid <i>id</i> · /iou nudge <i>id</i> · /iou cancel <i>id</i>")
    return "\n".join(lines)


def _mention(user_id: int | None, name: str) -> str:
    safe = html.escape(name)
    return f'<a href="tg://user?id={user_id}">{safe}</a>' if user_id else safe


async def iou_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_group(update):
        return
    msg = update.effective_message
    chat_id = update.effective_chat.id
    user = update.effective_user
    now = _time.time()
    args = list(context.args or [])
    sub = args[0].lower() if args else ""

    if sub in ("", "list", "ledger"):
        await msg.reply_html(ledger_text(db.iou_open(chat_id), now))
        return

    if sub in ("paid", "done", "settled", "settle") and len(args) == 2 and args[1].isdigit():
        r = db.iou_get(chat_id, int(args[1]))
        if r is None or r["settled_at"] is not None:
            await msg.reply_text("No open IOU with that id — see /ious.")
            return
        if user.id not in (r["debtor_id"], r["creditor_id"]) and r["debtor_id"] is not None:
            await msg.reply_text("Only the two parties can close this one.")
            return
        db.iou_settle(chat_id, r["id"], user.id, now)
        await msg.reply_html(random.choice(_PAID).format(
            debtor=html.escape(r["debtor_name"]), creditor=html.escape(r["creditor_name"]),
            text=html.escape(r["text"]),
        ))
        return

    if sub == "cancel" and len(args) == 2 and args[1].isdigit():
        r = db.iou_get(chat_id, int(args[1]))
        if r is None or r["settled_at"] is not None:
            await msg.reply_text("No open IOU with that id.")
            return
        if user.id != r["creditor_id"]:
            await msg.reply_text("Only the person owed can forgive a debt. Nice try.")
            return
        db.iou_delete(chat_id, r["id"])
        await msg.reply_html(
            f"🕊 {html.escape(r['creditor_name'])} forgives <b>{html.escape(r['text'])}</b>. "
            f"{html.escape(r['debtor_name'])} owes nothing but gratitude."
        )
        return

    if sub == "nudge" and len(args) == 2 and args[1].isdigit():
        r = db.iou_get(chat_id, int(args[1]))
        if r is None or r["settled_at"] is not None:
            await msg.reply_text("No open IOU with that id.")
            return
        if not db.iou_nudge(chat_id, r["id"], now, NUDGE_COOLDOWN):
            await msg.reply_text("That debt was nudged recently. Let the guilt marinate.")
            return
        await msg.reply_html(random.choice(_NUDGES).format(
            debtor=_mention(r["debtor_id"], r["debtor_name"]),
            creditor=html.escape(r["creditor_name"]), text=html.escape(r["text"]),
        ))
        return

    # ---- create: /iou @user <what>  |  /iou owe @user <what>  |  reply + /iou <what>
    i_owe = sub == "owe"
    if i_owe:
        args = args[1:]
    target_id, target_name = target_from_message(update, context)
    if target_id is None:
        await msg.reply_text(
            target_name or
            "Who owes what?\n"
            "/iou @user a coffee — they owe you\n"
            "/iou owe @user dinner — you owe them\n"
            "(or reply to their message with /iou <what>)"
        )
        return
    words = [a for a in args if not a.startswith("@")]
    text = " ".join(words).strip()[:120]
    if not text:
        await msg.reply_text("What's owed? /iou @user a coffee")
        return
    if target_id == user.id:
        await msg.reply_text("You can't owe yourself. That's called a to-do list.")
        return
    if i_owe:
        debtor, creditor = (user.id, user.first_name), (target_id, target_name)
    else:
        debtor, creditor = (target_id, target_name), (user.id, user.first_name)
    iou_id = db.iou_add(chat_id, debtor[0], debtor[1], creditor[0], creditor[1], text, "manual", now)
    await msg.reply_html(
        f"🧾 On the record (#{iou_id}): <b>{html.escape(debtor[1])}</b> owes "
        f"<b>{html.escape(creditor[1])}</b> <b>{html.escape(text)}</b>.\n"
        f"/iou paid {iou_id} when it's delivered."
    )


def get_handlers():
    return [
        CommandHandler("iou", iou_cmd),
        CommandHandler("ious", iou_cmd),
    ]
