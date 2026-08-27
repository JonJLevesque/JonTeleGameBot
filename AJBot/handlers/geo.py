"""/whereami — a geo-guessing round from the Beautiful Place photo pool.

One mystery photo, four country buttons. Guesses are secret until two
different people have answered; correct guessers earn a 🍪. Rounds are
short-lived, so in-flight state is in memory (a restart just voids the
round — run /whereami again).
"""
import html
import random

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import TelegramError
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

import db
from .beautiful import places
from .common import require_group

_rounds: dict[tuple[int, int], dict] = {}  # (chat_id, message_id) -> round


def _new_round():
    pool = [p for p in places() if p["country"]]
    place = random.choice(pool)
    countries = list({p["country"] for p in pool} - {place["country"]})
    options = random.sample(countries, 3) + [place["country"]]
    random.shuffle(options)
    return place, options


async def whereami(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_group(update):
        return
    distinct = {p["country"] for p in places() if p["country"]}
    if len(distinct) < 4:
        await update.effective_message.reply_text(
            "The photo pool is missing — run scripts/fetch_places.py first."
        )
        return
    place, options = _new_round()
    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton(c, callback_data=f"geo:{i}")]
         for i, c in enumerate(options)]
    )
    try:
        msg = await update.effective_message.reply_photo(
            place["img"],
            caption="🌍 <b>Where is this?</b>\nGuess the country — "
                    "answers reveal once two people have voted. Correct = 🍪",
            parse_mode="HTML", reply_markup=keyboard,
        )
    except TelegramError:  # rare unfetchable photo: draw again once
        place, options = _new_round()
        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton(c, callback_data=f"geo:{i}")]
             for i, c in enumerate(options)]
        )
        msg = await update.effective_message.reply_photo(
            place["img"], caption="🌍 <b>Where is this?</b>\nGuess the country!",
            parse_mode="HTML", reply_markup=keyboard,
        )
    _rounds[(update.effective_chat.id, msg.message_id)] = {
        "place": place, "options": options, "guesses": {},
    }


async def guess(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q.message is None:
        await q.answer()
        return
    key = (q.message.chat.id, q.message.message_id)
    rnd = _rounds.get(key)
    if rnd is None:
        await q.answer("This round is over (or predates my last restart).")
        return
    uid = q.from_user.id
    if uid in rnd["guesses"]:
        await q.answer("You've already locked in a guess!")
        return
    idx = int(q.data.split(":")[1])
    rnd["guesses"][uid] = (idx, q.from_user.first_name)
    if len(rnd["guesses"]) < 2:
        await q.answer("Locked in! Waiting for a second guesser…")
        return

    # Two guesses in: reveal.
    del _rounds[key]
    place, options = rnd["place"], rnd["options"]
    correct = place["country"]
    results = []
    for uid, (idx, name) in rnd["guesses"].items():
        right = options[idx] == correct
        if right:
            total = db.add_cookies(key[0], uid, 1, "whereami")
            results.append(f"✅ {html.escape(name)} — {html.escape(options[idx])} (+1 🍪, now {total})")
        else:
            results.append(f"❌ {html.escape(name)} — {html.escape(options[idx])}")
    await q.answer()
    caption = (
        f"🌍 It's <b>{html.escape(place['name'])}</b>, "
        f"{html.escape(correct)}!\n" + "\n".join(results) +
        "\n\nAnother? /whereami"
    )
    try:
        await q.edit_message_caption(caption, parse_mode="HTML")
    except TelegramError:
        pass


def get_handlers():
    return [
        CommandHandler("whereami", whereami),
        CallbackQueryHandler(guess, pattern=r"^geo:\d+$"),
    ]
