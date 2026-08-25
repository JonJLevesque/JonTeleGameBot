"""/daily and random supply drops — free cookies for showing up. 🎁

/daily is a once-a-day claim whose payout grows with a consecutive-day
streak. Drops are spontaneous: after enough chat activity the bot airdrops
a crate into the group; first to tap it keeps the contents — usually
cookies, occasionally bees.
"""
import html
import random
from datetime import datetime, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import TelegramError
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import db
from .common import LOCAL_TZ, require_group

# Daily payout: a small guaranteed base plus one bonus cookie per extra
# consecutive day, capped so a long streak is a habit, not an income.
DAILY_BASE = 2
DAILY_BONUS_CAP = 5  # day 6+ pays DAILY_BASE + DAILY_BONUS_CAP = 7


def daily_reward(streak: int) -> int:
    return DAILY_BASE + min(streak - 1, DAILY_BONUS_CAP)


class DropState:
    """Per-chat drop pacing: counts messages toward a random threshold and
    enforces the daily drop cap. Pure bookkeeping — the handler owns all
    Telegram and db side effects; rng and dates are injected for tests."""

    THRESHOLD_RANGE = (35, 60)  # messages between drops, redrawn each time
    DAILY_CAP = 3               # drops per chat per local day

    def __init__(self, rng=random):
        self.rng = rng
        self.count = 0
        self.threshold = rng.randint(*self.THRESHOLD_RANGE)
        self.day = None
        self.dropped_today = 0

    def register_message(self, now_date) -> bool:
        """Count one message; True when a drop should spawn now."""
        if now_date != self.day:
            self.day = now_date
            self.dropped_today = 0
        self.count += 1
        if self.count < self.threshold:
            return False
        self.count = 0
        self.threshold = self.rng.randint(*self.THRESHOLD_RANGE)
        if self.dropped_today >= self.DAILY_CAP:
            return False
        self.dropped_today += 1
        return True


TRAP_CHANCE = 0.2
AMOUNT_RANGE = (3, 8)


def roll_drop(rng=random) -> tuple[str, int]:
    kind = "trap" if rng.random() < TRAP_CHANCE else "crate"
    return kind, rng.randint(*AMOUNT_RANGE)


def trap_loss(amount: int, balance: int) -> int:
    """Bees can only take what you have — a balance never goes negative."""
    return min(amount, max(balance, 0))


_states: dict[int, DropState] = {}


# ------------------------------------------------------------------ handlers

async def daily_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_group(update):
        return
    msg = update.effective_message
    user = update.effective_user
    chat_id = update.effective_chat.id
    now = datetime.now(LOCAL_TZ).date()
    claimed, streak = db.daily_claim(
        chat_id, user.id, now.isoformat(), (now - timedelta(days=1)).isoformat()
    )
    if not claimed:
        await msg.reply_text(
            f"😴 You already claimed today's cookies — come back tomorrow. "
            f"(Streak: {streak} day{'s' if streak != 1 else ''}.)"
        )
        return
    reward = daily_reward(streak)
    total = db.add_cookies(chat_id, user.id, reward, "daily claim")
    if streak >= 3:
        tail = f"🔥 {streak}-day streak — keep it alive tomorrow!"
    elif streak == 2:
        tail = "Day 2 — one more for the 🔥."
    else:
        tail = "Day 1 — every streak starts somewhere."
    await msg.reply_text(
        f"🎁 Daily claimed: +{reward} 🍪 (now {total})\n{tail}"
    )


async def watch_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Group-4 observer on group text: paces and spawns supply drops."""
    chat_id = update.effective_chat.id
    st = _states.get(chat_id)
    if st is None:
        st = _states[chat_id] = DropState()
    if not st.register_message(datetime.now(LOCAL_TZ).date()):
        return
    kind, amount = roll_drop(st.rng)
    drop_id = db.create_drop(chat_id, kind, amount)
    btn = InlineKeyboardMarkup([[InlineKeyboardButton(
        "🎁 Open it!", callback_data=f"drop:{drop_id}"
    )]])
    try:
        await update.effective_message.reply_text(
            "🎁 A supply crate drops from the sky! "
            "First to tap it keeps whatever's inside…",
            reply_markup=btn,
        )
    except TelegramError:
        pass


async def drop_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    drop_id = int(query.data.split(":", 1)[1])
    user = query.from_user
    row = db.claim_drop(drop_id, user.id)
    if row is None:
        await query.answer("Too slow — already claimed!")
        return
    name = html.escape(user.first_name)
    if row["kind"] == "crate":
        total = db.add_cookies(row["chat_id"], user.id, row["amount"], "drop")
        await query.answer(f"+{row['amount']} 🍪!")
        text = f"📦 {name} opens the crate: +{row['amount']} 🍪 (now {total})."
    else:
        loss = trap_loss(row["amount"], db.get_cookies(row["chat_id"], user.id))
        await query.answer("BEES!")
        if loss:
            total = db.add_cookies(row["chat_id"], user.id, -loss, "drop trap")
            text = f"🐝 {name} opens the crate: BEES. −{loss} 🍪 (now {total})."
        else:
            text = (f"🐝 {name} opens the crate: BEES. "
                    f"Nothing to steal — poverty as armor.")
    try:
        await query.edit_message_text(text, parse_mode="HTML")
    except TelegramError:
        pass


def get_handlers():
    return [
        CommandHandler("daily", daily_cmd),
        # Group 4: observes group chatter without competing with taboo's
        # group-1 referee or the command handlers in group 0.
        (MessageHandler(
            filters.ChatType.GROUPS & filters.TEXT & ~filters.COMMAND,
            watch_messages,
        ), 4),
        CallbackQueryHandler(drop_callback, pattern=r"^drop:\d+$"),
    ]
