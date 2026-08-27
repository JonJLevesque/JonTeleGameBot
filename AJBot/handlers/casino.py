"""/slots and /blackjack — the cookie casino. 🎰

The economy's sink: both games are played against the house, so cookies
actually leave circulation (the shop and wagers only move them around).
Slots ride Telegram's native 🎰 dice — the animation runs client-side and
the value (1..64) is decided by Telegram's servers, so the house can't
cheat and neither can the pigeon. Blackjack is a full inline-button hand
persisted in casino_hands, so an in-progress hand survives a bot restart
(the stake is deducted at the deal and settled at the end).

House rules, posted at the door: slots pay 10x on 7️⃣7️⃣7️⃣, 5x on any
other triple, 1.5x when the first two reels match, stake back when the
last two do (RTP ≈ 86% — the pit-boss pigeon has expenses). Blackjack
pays 3:2, dealer stands on all 17s, double on your first decision only.
"""
import asyncio
import html
import json
import random
from collections import defaultdict

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

import db
from .common import require_group

SLOTS_MAX = 25
BJ_MAX = 50

_locks: dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)

_REEL = ("▫️", "🍇", "🍋", "7️⃣")  # telegram's slot symbols, digit order

SUITS = ("♠", "♥", "♦", "♣")
RANKS = ("A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K")


# ------------------------------------------------------------------- slots

def reels(value: int) -> tuple[int, int, int]:
    """Telegram's 🎰 dice value (1..64) as three base-4 reel digits."""
    v = value - 1
    return v % 4, v // 4 % 4, v // 16


def slots_payout(value: int, stake: int) -> tuple[float, str]:
    """(multiplier, label) for a spin. The table is chosen so the exact
    expected return over all 64 equally-likely values is 55/64 ≈ 0.859."""
    d0, d1, d2 = reels(value)
    if value == 64:
        return 10, "💰 JACKPOT! 7️⃣7️⃣7️⃣"
    if d0 == d1 == d2:
        return 5, "✨ Triple!"
    if d0 == d1:
        return 1.5, "So close — first two matched."
    if d1 == d2:
        return 1, "Consolation: stake back."
    return 0, "The house thanks you for your donation."


async def slots_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_group(update):
        return
    msg = update.effective_message
    user = update.effective_user
    chat_id = update.effective_chat.id

    args = context.args or []
    if not args or not args[0].isdecimal():
        await msg.reply_html(
            "🎰 <b>Slots</b> — <code>/slots &lt;stake&gt;</code> "
            f"(1–{SLOTS_MAX} 🍪)\n\n"
            "House rules: 7️⃣7️⃣7️⃣ pays 10x, any other triple 5x, first "
            "two reels matching 1.5x, last two matching returns your stake. "
            "Telegram spins the reels, not me — I just count the money."
        )
        return
    stake = int(args[0])
    if not 1 <= stake <= SLOTS_MAX:
        await msg.reply_text(
            f"The house takes stakes of 1–{SLOTS_MAX} 🍪, high roller."
        )
        return
    have = db.get_cookies(chat_id, user.id)
    if have < stake:
        await msg.reply_text(
            f"You only have {have} 🍪 — the house doesn't do credit."
        )
        return

    db.add_cookies(chat_id, user.id, -stake, "slots stake")
    try:
        dice_msg = await msg.reply_dice(emoji="🎰")
    except Exception:
        db.add_cookies(chat_id, user.id, stake, "slots refund")
        raise
    await asyncio.sleep(2)  # let the reels stop spinning

    value = dice_msg.dice.value
    mult, label = slots_payout(value, stake)
    winnings = int(stake * mult)
    if winnings:
        db.add_cookies(chat_id, user.id, winnings, "slots win")
    total = db.get_cookies(chat_id, user.id)
    d = reels(value)
    face = "".join(_REEL[i] for i in d)
    name = html.escape(user.first_name)
    net = winnings - stake
    outcome = (f"+{net}" if net > 0 else str(net)) + " 🍪"
    await dice_msg.reply_html(
        f"{face}  {label}\n"
        f"<b>{name}</b>: {outcome} (now {total})"
    )


# ---------------------------------------------------------------- blackjack
# Pure logic: cards are ints 0..51, rank = card % 13 (0 = A … 12 = K).

def fresh_deck() -> list[int]:
    deck = list(range(52))
    random.shuffle(deck)
    return deck


def hand_value(hand: list[int]) -> int:
    """Best blackjack total: aces count 11 when it fits, else 1."""
    total = sum(1 if c % 13 == 0 else min(c % 13 + 1, 10) for c in hand)
    if any(c % 13 == 0 for c in hand) and total + 10 <= 21:
        total += 10
    return total


def is_blackjack(hand: list[int]) -> bool:
    return len(hand) == 2 and hand_value(hand) == 21


def dealer_play(deck: list[int], dealer: list[int]) -> None:
    """House draws to 16, stands on all 17s."""
    while hand_value(dealer) < 17:
        dealer.append(deck.pop())


def settle(player: list[int], dealer: list[int], stake: int,
           doubled: bool, player_bj: bool) -> tuple[int, str]:
    """(cookies returned to the player, verdict). The stake was already
    deducted at the deal (twice if doubled), so 0 means the house keeps it."""
    pot = stake * 2 if doubled else stake
    pv, dv = hand_value(player), hand_value(dealer)
    dealer_bj = is_blackjack(dealer)
    if pv > 21:
        return 0, "💥 Bust. The house extends its condolences."
    if player_bj and dealer_bj:
        return pot, "🤝 Two blackjacks — push. Eerie."
    if player_bj:
        return int(pot * 2.5), "🃏 BLACKJACK! Paid 3:2, as is right and proper."
    if dealer_bj:
        return 0, "🃏 Dealer blackjack. The house always had it."
    if dv > 21:
        return pot * 2, "💥 Dealer busts! Take it and walk away."
    if pv > dv:
        return pot * 2, f"🏆 {pv} beats {dv}. The house nods respectfully."
    if pv < dv:
        return 0, f"🪦 {dv} beats {pv}. The house shows no emotion."
    return pot, f"🤝 Push at {pv}. Nobody's proud of this hand."


def _card(c: int) -> str:
    return f"{RANKS[c % 13]}{SUITS[c // 13]}"


def _hand_text(hand: list[int]) -> str:
    return " ".join(_card(c) for c in hand) + f"  ({hand_value(hand)})"


def _table_text(hand, state: dict, reveal: bool, footer: str) -> str:
    name = html.escape(state.get("name", "Player"))
    if reveal:
        dealer = _hand_text(state["dealer"])
    else:
        dealer = f"{_card(state['dealer'][0])} 🂠"
    pot = hand["stake"] * (2 if state.get("doubled") else 1)
    return (
        f"🃏 <b>Blackjack</b> — {name} vs the house (pot {pot} 🍪)\n\n"
        f"Dealer: {dealer}\n"
        f"{name}: {_hand_text(state['player'])}\n\n"
        f"{footer}"
    )


def _buttons(hand_id: int, can_double: bool) -> InlineKeyboardMarkup:
    row = [
        InlineKeyboardButton("🂠 Hit", callback_data=f"cas:{hand_id}:h"),
        InlineKeyboardButton("✋ Stand", callback_data=f"cas:{hand_id}:s"),
    ]
    if can_double:
        row.append(InlineKeyboardButton(
            "💰 Double", callback_data=f"cas:{hand_id}:d"))
    return InlineKeyboardMarkup([row])


async def _finish(query, hand, state: dict, player_bj: bool):
    if hand_value(state["player"]) <= 21 and not player_bj:
        dealer_play(state["deck"], state["dealer"])
    payout, verdict = settle(
        state["player"], state["dealer"], hand["stake"],
        state.get("doubled", False), player_bj,
    )
    db.update_casino_hand(hand["id"], state=state, status="finished")
    if payout:
        reason = ("blackjack push"
                  if payout == hand["stake"] * (2 if state.get("doubled") else 1)
                  else "blackjack win")
        db.add_cookies(hand["chat_id"], hand["user_id"], payout, reason)
    total = db.get_cookies(hand["chat_id"], hand["user_id"])
    await query.edit_message_text(
        _table_text(hand, state, reveal=True,
                    footer=f"{verdict}\nBalance: {total} 🍪"),
        parse_mode="HTML",
    )


async def blackjack_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_group(update):
        return
    msg = update.effective_message
    user = update.effective_user
    chat_id = update.effective_chat.id

    args = context.args or []
    if not args or not args[0].isdecimal():
        await msg.reply_html(
            "🃏 <b>Blackjack</b> — <code>/blackjack &lt;stake&gt;</code> "
            f"(1–{BJ_MAX} 🍪)\n\n"
            "Blackjack pays 3:2, dealer stands on all 17s, double on your "
            "first decision. The pit boss is a pigeon; he has seen everything."
        )
        return
    stake = int(args[0])
    if not 1 <= stake <= BJ_MAX:
        await msg.reply_text(f"Table stakes are 1–{BJ_MAX} 🍪.")
        return
    if db.active_casino_hand(chat_id, user.id):
        await msg.reply_text(
            "You already have a hand on the table — finish that one first."
        )
        return
    have = db.get_cookies(chat_id, user.id)
    if have < stake:
        await msg.reply_text(
            f"You only have {have} 🍪 — the house doesn't do credit."
        )
        return

    db.add_cookies(chat_id, user.id, -stake, "blackjack stake")
    deck = fresh_deck()
    state = {
        "deck": deck, "player": [deck.pop(), deck.pop()],
        "dealer": [deck.pop(), deck.pop()], "doubled": False,
        "name": user.first_name,
    }
    hand_id = db.create_casino_hand(chat_id, user.id, stake, state)
    hand = db.get_casino_hand(hand_id)

    if is_blackjack(state["player"]):
        # Instant 21 — settle immediately (dealer may push with their own).
        payout, verdict = settle(
            state["player"], state["dealer"], stake, False, True)
        db.update_casino_hand(hand_id, state=state, status="finished")
        if payout:
            reason = "blackjack push" if payout == stake else "blackjack win"
            db.add_cookies(chat_id, user.id, payout, reason)
        total = db.get_cookies(chat_id, user.id)
        await msg.reply_html(
            _table_text(hand, state, reveal=True,
                        footer=f"{verdict}\nBalance: {total} 🍪"))
        return

    can_double = have - stake >= stake
    await msg.reply_html(
        _table_text(hand, state, reveal=False,
                    footer="Your move. The dealer's hole card judges you."),
        reply_markup=_buttons(hand_id, can_double),
    )


async def blackjack_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    _, hand_id, action = query.data.split(":", 2)
    hand_id = int(hand_id)

    async with _locks[hand_id]:
        hand = db.get_casino_hand(hand_id)
        if hand is None or hand["status"] != "active":
            await query.answer("That hand is history.", show_alert=False)
            return
        if query.from_user.id != hand["user_id"]:
            await query.answer("Not your hand — the pit boss is watching.")
            return
        state = json.loads(hand["state"])
        first_decision = len(state["player"]) == 2 and not state["doubled"]

        if action == "h":
            state["player"].append(state["deck"].pop())
            if hand_value(state["player"]) > 21:
                await query.answer("Bust!")
                await _finish(query, hand, state, player_bj=False)
                return
            db.update_casino_hand(hand_id, state=state)
            await query.answer()
            await query.edit_message_text(
                _table_text(hand, state, reveal=False,
                            footer="Still standing. Your move."),
                parse_mode="HTML",
                reply_markup=_buttons(hand_id, can_double=False),
            )
        elif action == "d":
            if not first_decision:
                await query.answer("Doubling is a first-decision luxury.")
                return
            if db.get_cookies(hand["chat_id"], hand["user_id"]) < hand["stake"]:
                await query.answer(
                    f"You need {hand['stake']} more 🍪 to double.",
                    show_alert=True)
                return
            db.add_cookies(hand["chat_id"], hand["user_id"],
                           -hand["stake"], "blackjack stake")
            state["doubled"] = True
            state["player"].append(state["deck"].pop())
            await query.answer("Doubled down — one card, no regrets.")
            await _finish(query, hand, state, player_bj=False)
        elif action == "s":
            await query.answer()
            await _finish(query, hand, state, player_bj=False)
        else:
            await query.answer()


def get_handlers():
    return [
        CommandHandler("slots", slots_cmd),
        CommandHandler("blackjack", blackjack_cmd),
        CallbackQueryHandler(blackjack_callback, pattern=r"^cas:\d+:"),
    ]
