"""Shared relationship XP and levels — /level. 💞

XP is a purely derived metric: nothing is instrumented and no XP is ever
"granted". Every feature already records its activity in SQLite — finished
games, wordle plays, taboo rounds, archived quotes, delivered whispers,
the cookie ledger — so the chat's level is just a weighted read over
everything the two of you have already done together, past included. Any
future feature that writes to the db feeds the level for free.

A ten-minute watcher announces newly reached levels in the chat; on its
first ever run an established chat jumps straight to its true accumulated
level in one big announcement, which is the correct amount of drama.
"""
import html
import random

from telegram import Update
from telegram.error import TelegramError
from telegram.ext import CommandHandler, ContextTypes

import db
from .common import require_group

# Effortful shared activities weigh more than passive ledger ticks.
WEIGHTS = {
    "games": 40, "taboo": 25, "wordle": 15, "paranoia": 15,
    "quotes": 12, "dailyq": 12, "whispers": 8, "cookie_moves": 2,
}

LABELS = {
    "games": "board games", "taboo": "taboo", "wordle": "wordle",
    "paranoia": "paranoia", "quotes": "quotes", "dailyq": "daily questions",
    "whispers": "whispers", "cookie_moves": "cookie ledger",
}

TITLES = [
    "Acquaintances",
    "Partners in Crime",
    "Co-Conspirators",
    "A Known Duo",
    "Menaces (Jointly)",
    "Attached at the Hip",
    "Disgustingly Cute",
    "The Chat Has Noticed",
    "Finishing Each Other's Sentences",
    "A Two-Person Cult",
    "Legally Inseparable",
    "One Braincell, Shared",
    "Annoyingly Telepathic",
    "Beyond Counseling",
    "A Single Legal Entity",
    "Soulbound (Patch Notes Pending)",
]

_FLOURISHES = [
    "The relationship has been recompiled with new features.",
    "Somewhere, a scrapbook just updated itself.",
    "This milestone was earned one questionable decision at a time.",
    "The pigeon has filed the paperwork. It's official.",
]


def xp_for_level(level: int) -> int:
    """Total XP needed to reach a level: 150 · n(n+1)/2 — early levels land
    in days, later ones take months."""
    return 150 * level * (level + 1) // 2


def level_for_xp(total: int) -> int:
    level = 0
    while total >= xp_for_level(level + 1):
        level += 1
    return level


def title(level: int) -> str:
    return TITLES[min(level, len(TITLES) - 1)]


def weighted_sources(chat_id: int) -> dict[str, int]:
    """Each activity's weighted XP contribution."""
    stats = db.xp_stats(chat_id)
    return {k: stats[k] * w for k, w in WEIGHTS.items()}


def xp(chat_id: int) -> int:
    return sum(weighted_sources(chat_id).values())


async def level_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_group(update):
        return
    chat_id = update.effective_chat.id
    sources = weighted_sources(chat_id)
    total = sum(sources.values())
    level = level_for_xp(total)
    floor, ceiling = xp_for_level(level), xp_for_level(level + 1)
    filled = int(10 * (total - floor) / (ceiling - floor))
    bar = "▰" * filled + "▱" * (10 - filled)
    lines = [
        f"💞 <b>Level {level}: {title(level)}</b>",
        f"{bar}  {total:,} XP — next level at {ceiling:,}",
    ]
    top = sorted(
        ((k, v) for k, v in sources.items() if v),
        key=lambda kv: kv[1], reverse=True,
    )[:3]
    if top:
        lines.append(
            "Top sources: " + " · ".join(f"{LABELS[k]} {v:,}" for k, v in top)
        )
    else:
        lines.append("No XP yet — go play something.")
    await update.effective_message.reply_html("\n".join(lines))


async def _watch_job(context: ContextTypes.DEFAULT_TYPE):
    for chat_id in db.chats_with_min_members(2):
        level = level_for_xp(xp(chat_id))
        if level <= db.get_announced_level(chat_id):
            continue
        # Record first, then post: a send failure must never re-announce.
        db.set_announced_level(chat_id, level)
        try:
            await context.bot.send_message(
                chat_id,
                f"🎉 <b>Level {level} unlocked: {html.escape(title(level))}</b>\n"
                f"{random.choice(_FLOURISHES)}\n(/level for the ledger)",
                parse_mode="HTML",
            )
        except TelegramError:
            continue


def schedule(app) -> None:
    app.job_queue.run_repeating(
        _watch_job, interval=600, first=30, name="level-watch"
    )


def get_handlers():
    return [CommandHandler("level", level_cmd)]
