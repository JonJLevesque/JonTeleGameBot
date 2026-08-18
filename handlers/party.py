"""Party games: /truthordare, /wouldyourather, /paranoia.

Paranoia works without requiring players to have DMed the bot: the question
is delivered through a callback alert that only the target player can open
(callback answers are visible solely to the user who pressed the button).
The target then answers aloud in the chat and either flips the coin (50%
chance the question is revealed to everyone) or refuses and takes a dare.
"""
import html
import random

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

import ai
import db
import prompts
from .common import is_duo_chat, require_group, target_from_message


async def _draw(category: str, update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """Produce a prompt for this chat: AI-generated when a Claude API key is
    configured, otherwise (or on any AI failure) drawn from the static banks.

    The pool adapts to the chat: two-person chats get the duo banks, group
    chats the group banks; /spicymode adds the 18+ pool. {subject} is filled
    with a random other member's name; if nobody else is known yet, those
    prompts are skipped."""
    chat_id = update.effective_chat.id
    user = update.effective_user
    duo = await is_duo_chat(update, context)
    spicy = db.is_spicy(chat_id)
    others = db.random_known_users(chat_id, exclude_ids=(user.id,), limit=1)
    subject = others[0][1] if others else None

    if ai.ENABLED:
        await context.bot.send_chat_action(chat_id, ChatAction.TYPING)
        generated = await ai.generate(
            category, chat_id, duo=duo, spicy=spicy,
            user_name=user.first_name, subject=subject,
        )
        if generated:
            return generated

    pool = prompts.pool(category, duo=duo, spicy=spicy)
    if subject is None:
        pool = [p for p in pool if "{subject}" not in p]
    prompt = random.choice(pool)
    if "{subject}" in prompt:
        prompt = prompt.format(subject=subject)
    return prompt


async def truth_or_dare(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.effective_user.first_name
    if random.random() < 0.5:
        prompt = await _draw("truth", update, context)
        text = f"🗣 <b>Truth</b> for {name}:\n{html.escape(prompt)}"
    else:
        prompt = await _draw("dare", update, context)
        text = f"🔥 <b>Dare</b> for {name}:\n{html.escape(prompt)}"
    await update.effective_message.reply_html(text)


async def would_you_rather(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prompt = await _draw("wyr", update, context)
    await update.effective_message.reply_html(
        f"🤔 <b>Would you rather…</b>\n{html.escape(prompt)}"
    )


async def paranoia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_group(update):
        return
    chat_id = update.effective_chat.id
    sender = update.effective_user

    # Target: replied-to user / @username arg, else a random known member.
    target_id, target_name = target_from_message(update, context)
    if target_id is None and target_name is not None:
        await update.effective_message.reply_text(target_name)  # resolution error
        return
    if target_id is None:
        candidates = db.random_known_users(chat_id, exclude_ids=(), limit=1)
        target_id, target_name = candidates[0] if candidates else (sender.id, sender.first_name)

    # Subject: a random member other than the target, if the question needs one.
    others = db.random_known_users(chat_id, exclude_ids=(target_id,), limit=1)
    subject = others[0][1] if others else None
    duo = await is_duo_chat(update, context)

    question = None
    if ai.ENABLED:
        await context.bot.send_chat_action(chat_id, ChatAction.TYPING)
        question = await ai.generate(
            "paranoia", chat_id, duo=duo, spicy=db.is_spicy(chat_id),
            user_name=target_name, subject=subject,
        )
    if not question:
        pool = prompts.PARANOIA_QUESTIONS
        if duo and subject:
            # "Who in this chat" questions are pointless with two people —
            # keep only the ones about a specific person.
            pool = [q for q in pool if "{subject}" in q]
        elif subject is None:
            pool = [q for q in pool if "{subject}" not in q]
        question = random.choice(pool)
        if "{subject}" in question:
            question = question.format(subject=subject)

    round_id = db.create_paranoia(chat_id, target_id, target_name, question)
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("👀 View question (secret)", callback_data=f"pn:{round_id}:v")],
        [InlineKeyboardButton("🗣 I answered aloud — flip the coin", callback_data=f"pn:{round_id}:a")],
        [InlineKeyboardButton("🙅 Refuse (take a dare)", callback_data=f"pn:{round_id}:r")],
    ])
    await update.effective_message.reply_html(
        f"🤫 <b>Paranoia!</b>\n"
        f"<b>{target_name}</b>, a secret question awaits — only you can view it.\n"
        f"Answer it out loud in the chat, then flip the coin: heads, the question "
        f"gets revealed to everyone; tails, it stays secret forever. "
        f"Too spicy? Refuse and take a dare instead.",
        reply_markup=keyboard,
    )


async def paranoia_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    _, round_id, action = query.data.split(":")
    rnd = db.get_paranoia(int(round_id))
    if rnd is None:
        await query.answer("This round has expired.", show_alert=True)
        return
    if query.from_user.id != rnd["target_id"]:
        await query.answer(f"Only {rnd['target_name']} can use these buttons! 🤫")
        return
    if rnd["stage"] == "done":
        await query.answer("This round is over.")
        return

    if action == "v":
        await query.answer(f"🤫 {rnd['question']}", show_alert=True)
        return

    db.finish_paranoia(rnd["id"])
    if action == "a":
        if random.random() < 0.5:
            result = (
                f"🪙 The coin lands on <b>heads</b> — the question is revealed!\n"
                f"<b>{rnd['target_name']}</b> was asked:\n“{rnd['question']}”"
            )
        else:
            result = (
                f"🪙 The coin lands on <b>tails</b> — the question stays secret forever. "
                f"Stay paranoid. 👀"
            )
    else:  # refuse
        result = (
            f"🙅 <b>{rnd['target_name']}</b> refused to answer! The question stays "
            f"secret, but the price is a dare:\n🔥 {random.choice(prompts.DARES)}"
        )
    await query.answer()
    await query.edit_message_text(
        f"{query.message.text_html}\n\n{result}", parse_mode="HTML"
    )


def get_handlers():
    return [
        CommandHandler("truthordare", truth_or_dare),
        CommandHandler("wouldyourather", would_you_rather),
        CommandHandler("paranoia", paranoia),
        CallbackQueryHandler(paranoia_callback, pattern=r"^pn:\d+:[var]$"),
    ]
