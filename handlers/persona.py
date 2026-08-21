"""The bot's voice. 🐦

Reply to one of the bot's messages or @mention it in a group and it answers
in character — a carrier-pigeon concierge who knows the standings. Very
rarely, it butts in unprompted. It dotes on the chat members and treats its
operator (config.ADMIN_ID) with long-suffering butler energy — and it is
discreet about the difference.

Rate-limit philosophy: the bot speaking should feel like a treat, never
like a third phone in the room. Hence a per-chat cooldown, a daily cap,
and an unprompted-interjection gate (a long quiet stretch of human chatter
plus a small dice roll). Without an API key it answers direct mentions
from a tiny canned bank and never interjects. All limits are in-memory:
a restart forgetting them is harmless.
"""
import random
import time
from collections import defaultdict, deque
from datetime import date

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes, MessageHandler, filters

import ai
import config
import db
from . import birthday, brain
from .common import GROUP_TYPES
from .wordle import _streak as wordle_streak

COOLDOWN_SECONDS = 15
DAILY_CAP = 40
INTERJECT_AFTER = 30    # human messages since the bot last spoke
INTERJECT_CHANCE = 0.021  # dialed back 30% from 0.03 by operator request

# Two banks, one per register (see is_operator): the pigeon dotes on the
# members and long-suffers the management.
CANNED_WARM = [
    "Coo. For you? Anything.",
    "Correct as usual — I checked the records.",
    "Objectively the better half of this chat. I keep the stats.",
    "You could tell me anything and I'd carry it to my grave.",
    "I'd fly through weather for you. I won't, for everyone.",
    "Noted, cherished, filed under “right again”.",
    "You have my vote, my cookie, and my wing.",
    "Say the word and the court leans your way.",
]
CANNED_BUTLER = [
    "I'm a carrier pigeon, not a therapist. …but go on.",
    "I heard my name. I always hear my name. Sigh.",
    "My lawyer says I can't comment without a cookie retainer.",
    "Take it to the court — /settle. Don't expect much.",
    "I'd weigh in, but I'm carrying six undelivered secrets right now.",
    "Bold words from someone who hasn't finished today's /wordle.",
    "I run the games, the mail and the economy here. This too, apparently.",
    "Yes, yes. Right away. Coo.",
]

_context: dict[int, deque] = defaultdict(lambda: deque(maxlen=15))
_since_bot: dict[int, int] = defaultdict(int)


# ---------------------------------------------------- pure decision helpers

def is_addressed(text: str, reply_is_to_bot: bool, bot_username: str) -> bool:
    """The bot is spoken to: a reply to one of its messages, or an @mention."""
    if reply_is_to_bot:
        return True
    return f"@{bot_username}".lower() in (text or "").lower()


def should_interject(msgs_since_bot: int, rng_value: float,
                     ai_enabled: bool) -> bool:
    """Unprompted interjections need AI (canned lines only answer direct
    mentions), a long human-only stretch, and luck."""
    return (ai_enabled and msgs_since_bot >= INTERJECT_AFTER
            and rng_value < INTERJECT_CHANCE)


def is_operator(user_id: int) -> bool:
    """The bot operator gets the butler register. With no ADMIN_ID set,
    nobody is the operator and everyone gets the warmth."""
    return config.ADMIN_ID != 0 and user_id == config.ADMIN_ID


def canned_line(operator: bool, rng=random) -> str:
    return rng.choice(CANNED_BUTLER if operator else CANNED_WARM)


class RateLimiter:
    """Per-chat cooldown + daily cap, with injectable clocks for tests."""

    def __init__(self, cooldown: float = COOLDOWN_SECONDS,
                 cap: int = DAILY_CAP):
        self.cooldown, self.cap = cooldown, cap
        self._last: dict[int, float] = {}
        self._counts: dict[int, tuple[str, int]] = {}  # chat -> (day, n)

    def allow(self, chat_id: int, now: float, today: str) -> bool:
        last = self._last.get(chat_id)
        if last is not None and now - last < self.cooldown:
            return False
        day, n = self._counts.get(chat_id, (today, 0))
        return day != today or n < self.cap

    def record(self, chat_id: int, now: float, today: str) -> None:
        self._last[chat_id] = now
        day, n = self._counts.get(chat_id, (today, 0))
        self._counts[chat_id] = (today, n + 1 if day == today else 1)


_limiter = RateLimiter()


# ------------------------------------------------------------------ context

def _standings(chat_id: int) -> str | None:
    """A small factual block for the model. Best-effort: a failure here must
    never cost the chat a reply."""
    try:
        lines = []
        board = db.cookie_leaderboard(chat_id)
        if board:
            lines.append(
                "Cookies: " + ", ".join(f"{n} {c}🍪" for n, c in board)
            )
        for m in db.chat_members(chat_id):
            wins = db.wordle_duel_wins(chat_id, m["user_id"])
            lines.append(
                f"{m['first_name']}: {wins} wordle duel wins, "
                f"current streak {wordle_streak(m['user_id'])}"
            )
            if birthday.is_birthday_today(m["user_id"]):
                lines.append(
                    f"🎂 TODAY IS {m['first_name'].upper()}'S BIRTHDAY — "
                    f"celebrate them relentlessly in every reply."
                )
        return "\n".join(lines) or None
    except Exception:
        return None


# ------------------------------------------------------------------ handler

async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    msg = update.effective_message
    user = update.effective_user
    if (chat is None or chat.type not in GROUP_TYPES or msg is None
            or not msg.text or user is None or user.is_bot):
        return

    _context[chat.id].append(f"{user.first_name}: {msg.text[:200]}")
    _since_bot[chat.id] += 1

    reply_to_bot = bool(
        msg.reply_to_message and msg.reply_to_message.from_user
        and msg.reply_to_message.from_user.id == context.bot.id
    )
    addressed = is_addressed(msg.text, reply_to_bot, context.bot.username)
    if not addressed and not should_interject(
            _since_bot[chat.id], random.random(), ai.ENABLED):
        return
    now, today = time.monotonic(), date.today().isoformat()
    if not _limiter.allow(chat.id, now, today):
        return

    # The butler register is suspended on the operator's own birthday.
    operator = is_operator(user.id) and not birthday.is_birthday_today(user.id)

    # Direct memory instructions ("@bot remember ...") are handled
    # deterministically — they must work even with no API key, and a
    # "remember X" must never be paraphrased away by the model.
    if addressed:
        bare = msg.text.replace(f"@{context.bot.username}", "").strip()
        instruction = brain.parse_instruction(bare)
        if instruction:
            await msg.reply_text(
                brain.handle_instruction(chat.id, *instruction)
            )
            _limiter.record(chat.id, now, today)
            _since_bot[chat.id] = 0
            return

    if ai.ENABLED:
        await context.bot.send_chat_action(chat.id, ChatAction.TYPING)
        reply = await ai.converse(
            chat.id,
            user_name=user.first_name,
            text=msg.text[:400],
            context_lines=list(_context[chat.id]),
            standings=_standings(chat.id),
            spicy=db.is_spicy(chat.id),
            is_operator=operator,
            memories=db.relevant_memories(chat.id, msg.text),
        )
    elif addressed:
        reply = canned_line(operator)
    else:
        return

    if reply:
        # The model may file facts it was told: [[remember: ...]] markers.
        reply, facts = brain.strip_markers(reply)
        for fact in facts:
            db.add_memory(chat.id, fact, "told")
    if not reply:
        if not addressed:
            return  # a failed interjection dies quietly
        # A direct mention deserves an answer even when the model bails.
        reply = canned_line(operator)
    await msg.reply_text(reply)
    _limiter.record(chat.id, now, today)
    _since_bot[chat.id] = 0
    _context[chat.id].append(f"(you): {reply[:200]}")


def get_handlers():
    # Group 3: observes every group message without competing with taboo's
    # group-1 referee or the group-0 commands.
    return [
        (MessageHandler(
            filters.ChatType.GROUPS & filters.TEXT & ~filters.COMMAND,
            on_message,
        ), 3),
    ]
