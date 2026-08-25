"""IOU shop: turn cookies into real-world favors.

The chat defines its own rewards (/shop add 50 loser cooks dinner); anyone
can then /redeem one with their cookie balance. The bot announces the
redemption so the debt is on the record.
"""
import html
import time as _time

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

import db
from .common import is_duo_chat, require_group


async def shop_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_group(update):
        return
    msg = update.effective_message
    chat_id = update.effective_chat.id
    args = context.args or []

    if args and args[0].lower() == "add":
        if len(args) < 3 or not args[1].isdigit() or int(args[1]) < 1:
            await msg.reply_text(
                "Usage: /shop add <price> <reward…>\n"
                "e.g. /shop add 50 loser cooks dinner"
            )
            return
        price, reward = int(args[1]), " ".join(args[2:])[:200]
        owner = update.effective_user
        item_id = db.shop_add(chat_id, price, reward, owner.id, owner.first_name)
        await msg.reply_html(
            f"🛍 Added to the shop: <b>{html.escape(reward)}</b> — "
            f"{price} 🍪 (#{item_id}). When someone redeems it, "
            f"{html.escape(owner.first_name)} delivers."
        )
        return

    if args and args[0].lower() == "remove":
        if len(args) < 2 or not args[1].isdigit():
            await msg.reply_text("Usage: /shop remove <id>")
            return
        if db.shop_remove(chat_id, int(args[1])):
            await msg.reply_text("🗑 Removed.")
        else:
            await msg.reply_text("No item with that id in this chat's shop.")
        return

    items = db.shop_list(chat_id)
    if not items:
        await msg.reply_text(
            "🛍 The shop is empty! Stock it with real-world rewards:\n"
            "/shop add 50 loser cooks dinner\n"
            "/shop add 100 winner picks the next trip\n"
            "Then buy them with /redeem <id>."
        )
        return
    lines = ["🛍 <b>Cookie shop</b> — buy with /redeem <i>id</i>"]
    for it in items:
        owner = f" <i>(from {html.escape(it['owner_name'])})</i>" if it["owner_name"] else ""
        lines.append(f"#{it['id']} · <b>{html.escape(it['reward'])}</b> — {it['price']} 🍪{owner}")
    balance = db.get_cookies(chat_id, update.effective_user.id)
    lines.append(f"\nYour balance: {balance} 🍪")
    await msg.reply_html("\n".join(lines))


def debtor_for(item, buyer_id: int, chat_id: int, duo: bool) -> tuple[int | None, str]:
    """Who delivers a redeemed reward: the item's owner, unless the buyer
    owns it; in a two-person chat that means the other person; otherwise the
    chat collectively (nobody in particular gets nudged)."""
    if item["owner_id"] and item["owner_id"] != buyer_id:
        return item["owner_id"], item["owner_name"]
    if duo:
        others = db.random_known_users(chat_id, exclude_ids=(buyer_id,), limit=1)
        if others:
            return others[0]
    return None, "the chat"


async def redeem_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_group(update):
        return
    msg = update.effective_message
    chat_id = update.effective_chat.id
    user = update.effective_user
    args = context.args or []
    if not args or not args[0].isdigit():
        await msg.reply_text("Usage: /redeem <id> — see /shop for the catalog.")
        return
    item = db.shop_get(chat_id, int(args[0]))
    if item is None:
        await msg.reply_text("No item with that id — check /shop.")
        return
    balance = db.get_cookies(chat_id, user.id)
    if balance < item["price"]:
        await msg.reply_text(
            f"You have {balance} 🍪 but this costs {item['price']} 🍪. "
            f"Go win some games!"
        )
        return
    total = db.add_cookies(chat_id, user.id, -item["price"],
                           f"redeemed: {item['reward']}")
    debtor_id, debtor_name = debtor_for(item, user.id, chat_id,
                                        await is_duo_chat(update, context))
    iou_id = db.iou_add(chat_id, debtor_id, debtor_name, user.id, user.first_name,
                        item["reward"], "shop", _time.time())
    safe_name = html.escape(user.first_name)
    await msg.reply_html(
        f"🧾 <b>REDEEMED!</b> {safe_name} cashed in "
        f"<b>{item['price']} 🍪</b> for:\n"
        f"✨ <b>{html.escape(item['reward'])}</b> ✨\n"
        f"IOU #{iou_id}: <b>{html.escape(debtor_name)}</b> owes {safe_name}. "
        f"/iou paid {iou_id} once delivered. ({safe_name}: {total} 🍪 left)"
    )


def get_handlers():
    return [
        CommandHandler("shop", shop_cmd),
        CommandHandler("redeem", redeem_cmd),
    ]
