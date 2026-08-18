"""Roleplay scenario generator (/roleplay) and the Spicy🌶️ toggle (/spicymode).

/roleplay picks a random scenario and hands random roles to up to four chat
members (the command sender always gets one; the rest come from the cached
member list). The group acts it out in chat.

/spicymode on|off is restricted to chat admins and unlocks the Spicy🌶️ prompt
pools for /truthordare, /wouldyourather and /roleplay in that chat.
"""
import html
import random

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import CommandHandler, ContextTypes

import ai
import db
import prompts
from .common import is_chat_admin, is_duo_chat, require_group

MAX_PLAYERS = 4


async def roleplay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_group(update):
        return
    chat_id = update.effective_chat.id
    sender = update.effective_user
    duo = await is_duo_chat(update, context)
    spicy = db.is_spicy(chat_id)

    players = [(sender.id, sender.first_name)]
    players += db.random_known_users(chat_id, exclude_ids=(sender.id,),
                                     limit=MAX_PLAYERS - 1)
    names = [name for _, name in players]

    body = None
    if ai.ENABLED:
        await context.bot.send_chat_action(chat_id, ChatAction.TYPING)
        body = await ai.generate(
            "roleplay", chat_id, duo=duo, spicy=spicy,
            user_name=sender.first_name, names=names,
        )
        if body:
            body = html.escape(body)

    if not body:
        scenarios = list(prompts.ROLEPLAY_SCENARIOS)
        if duo:
            scenarios += prompts.ROLEPLAY_SCENARIOS_DUO
        if spicy:
            scenarios += prompts.ROLEPLAY_SCENARIOS_SPICY
        scenario = random.choice(scenarios)
        roles = random.sample(prompts.ROLEPLAY_ROLES, k=len(players))
        cast = "\n".join(
            f"• <b>{name}</b> — {role}" for (_, name), role in zip(players, roles)
        )
        body = f"<i>{scenario}</i>\n\n{cast}"

    lines = ["🎭 <b>Roleplay</b>", body]
    if len(players) == 1:
        lines.append("\n(I only know members who've spoken — once more people "
                     "chat, I can cast them too.)")
    await update.effective_message.reply_html("\n".join(lines))


async def spicy_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_group(update):
        return
    chat_id = update.effective_chat.id
    arg = (context.args[0].lower() if context.args else "")
    if arg not in ("on", "off"):
        state = "ON 🌶" if db.is_spicy(chat_id) else "off"
        await update.effective_message.reply_text(
            f"Spicy🌶️ mode is currently {state}.\n"
            "Chat admins can change it with /spicymode on or /spicymode off."
        )
        return
    if not await is_chat_admin(update, context):
        await update.effective_message.reply_text(
            "Only chat admins can toggle spicy mode."
        )
        return
    db.set_spicy(chat_id, arg == "on")
    if arg == "on":
        await update.effective_message.reply_text(
            "Spicy🌶️ mode is ON for this chat — flirtier prompts are now "
            "in the mix for /truthordare, /wouldyourather and /roleplay. "
            "Admins: make sure everyone here is an adult and on board."
        )
    else:
        await update.effective_message.reply_text(
            "🧊 Spicy mode is OFF — back to family-friendly prompts."
        )


def get_handlers():
    return [
        CommandHandler("roleplay", roleplay),
        CommandHandler("spicymode", spicy_mode),
    ]
