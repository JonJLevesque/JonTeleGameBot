"""Taboo-style phrase game: /taboo.

The bot whispers a secret phrase to the describer (same only-you-can-open
callback-alert trick as Paranoia). The describer must get the chat to guess
the phrase WITHOUT using any of its words, and gets at most 3 clue messages.
A message listener does the refereeing automatically:

  * every plain-text message from the describer counts as a clue (1/3, 2/3…);
    a 4th one loses the round,
  * a clue containing any key word of the phrase loses the round instantly
    (stopwords like "but"/"no" are fair game — see STOPWORDS),
  * any other member whose message contains the phrase wins the round —
    guesser and describer each earn a cookie.

This needs the bot to see regular messages, i.e. BotFather privacy mode
disabled (see README). One round per chat at a time.
"""
import random
import re

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import ai
import db
import prompts
from .common import GROUP_TYPES, is_duo_chat, require_group

MAX_CLUES = 3

# Little grammar words are fair game in clues — otherwise a phrase like
# "seen but no reply" forbids "but" and "no" and clues become impossible.
# Only the meaningful words of the phrase lose the round.
STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "for", "if",
    "in", "is", "it", "its", "me", "my", "no", "not", "of", "on", "or",
    "so", "the", "to", "was", "we", "you", "your", "i",
}


def _words(text: str) -> list[str]:
    return re.findall(r"[\w']+", text.lower())


def _forbidden(phrase: str) -> set[str]:
    words = set(_words(phrase))
    meaningful = words - STOPWORDS
    return meaningful or words  # never an empty forbidden set


async def start_taboo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_group(update):
        return
    chat_id = update.effective_chat.id
    if db.get_active_taboo(chat_id):
        await update.effective_message.reply_text(
            "A Taboo round is already running here — finish it first "
            "(or the describer can tap 🏳️ Give up)."
        )
        return
    describer = update.effective_user
    spicy = db.is_spicy(chat_id)
    phrase = None
    if ai.ENABLED:
        await context.bot.send_chat_action(chat_id, ChatAction.TYPING)
        raw = await ai.generate(
            "taboo", chat_id, duo=await is_duo_chat(update, context),
            spicy=spicy, user_name=describer.first_name,
        )
        if raw:
            raw = raw.strip().strip('"“”.').lower()
            # only accept a sane, playable phrase; otherwise use the bank
            if 2 <= len(_words(raw)) <= 5 and len(raw) <= 40:
                phrase = raw
    if phrase is None:
        bank = list(prompts.TABOO_PHRASES)
        if spicy:
            bank += prompts.TABOO_PHRASES_SPICY
        phrase = random.choice(bank)
    round_id = db.create_taboo(chat_id, describer.id, describer.first_name, phrase)
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("👀 View my secret phrase", callback_data=f"tb:{round_id}:v")],
        [InlineKeyboardButton("🏳️ Give up (reveal)", callback_data=f"tb:{round_id}:g")],
    ])
    await update.effective_message.reply_html(
        f"🤐 <b>Taboo!</b>\n"
        f"<b>{describer.first_name}</b> has a secret phrase and must make you "
        f"guess it — without using its <i>key words</i> (little words like "
        f"“but” and “no” are fine), in at most "
        f"<b>{MAX_CLUES} clue messages</b>.\n\n"
        f"Everyone else: type your guesses right here in the chat. "
        f"Correct guess = 🍪 for the guesser <i>and</i> the describer!",
        reply_markup=keyboard,
    )


async def taboo_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    _, round_id, action = query.data.split(":")
    rnd = db.get_taboo(int(round_id))
    if rnd is None:
        await query.answer("This round has expired.", show_alert=True)
        return
    if query.from_user.id != rnd["describer_id"]:
        await query.answer(f"Only {rnd['describer_name']} can use these buttons!")
        return
    if rnd["stage"] == "done":
        await query.answer("This round is over.")
        return

    if action == "v":
        banned = ", ".join(sorted(_forbidden(rnd["phrase"])))
        await query.answer(
            f"🤫 Your phrase: “{rnd['phrase']}”\n"
            f"Forbidden words: {banned}\n"
            f"Clues used: {rnd['clues_used']}/{MAX_CLUES}",
            show_alert=True,
        )
        return

    # action == "g": give up
    db.finish_taboo(rnd["id"])
    await query.answer()
    await query.edit_message_text(
        f"🏳️ <b>{rnd['describer_name']}</b> gave up! "
        f"The phrase was: “<b>{rnd['phrase']}</b>”",
        parse_mode="HTML",
    )


async def referee(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Watches group messages while a round is active and referees it."""
    chat = update.effective_chat
    msg = update.effective_message
    user = update.effective_user
    if chat.type not in GROUP_TYPES or not msg.text or user is None or user.is_bot:
        return
    rnd = db.get_active_taboo(chat.id)
    if rnd is None:
        return

    msg_words = _words(msg.text)

    if user.id == rnd["describer_id"]:
        forbidden = _forbidden(rnd["phrase"]) & set(msg_words)
        if forbidden:
            db.finish_taboo(rnd["id"])
            await msg.reply_html(
                f"🚨 <b>{rnd['describer_name']}</b> said a forbidden word "
                f"(“{sorted(forbidden)[0]}”)! Round lost — the phrase was: "
                f"“<b>{rnd['phrase']}</b>”"
            )
            return
        clues = db.bump_taboo_clues(rnd["id"])
        if clues > MAX_CLUES:
            db.finish_taboo(rnd["id"])
            await msg.reply_html(
                f"⏱ That was one message too many — only {MAX_CLUES} clues allowed! "
                f"The phrase was: “<b>{rnd['phrase']}</b>”"
            )
        elif clues == MAX_CLUES:
            await msg.reply_text(
                f"🗣 Clue {clues}/{MAX_CLUES} — that's the last one! Guesses only now."
            )
        else:
            await msg.reply_text(f"🗣 Clue {clues}/{MAX_CLUES}")
        return

    # Anyone else: check for a correct guess (phrase contained in the message).
    if " ".join(_words(rnd["phrase"])) in " ".join(msg_words):
        db.finish_taboo(rnd["id"])
        db.add_cookies(chat.id, user.id, 1)
        db.add_cookies(chat.id, rnd["describer_id"], 1)
        await msg.reply_html(
            f"🎉 <b>{user.first_name}</b> got it! The phrase was: "
            f"“<b>{rnd['phrase']}</b>”\n"
            f"🍪 +1 cookie each for {user.first_name} and {rnd['describer_name']}!"
        )


def get_handlers():
    return [
        CommandHandler("taboo", start_taboo),
        CallbackQueryHandler(taboo_callback, pattern=r"^tb:\d+:[vg]$"),
        # Group 1 so it never competes with command handlers in group 0.
        (MessageHandler(filters.TEXT & ~filters.COMMAND, referee), 1),
    ]
