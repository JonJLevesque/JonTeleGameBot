"""The bot's memory. 🧠

Three ways facts get in: tell it directly ("@bot remember cherry hates
olives" — deterministic, works without an API key), the persona quietly
files things it's told mid-conversation (via [[remember: ...]] markers in
its replies), and a background harvester that skims recent chat a few
times a day for durable facts (preferences, nicknames, in-jokes, plans).

Transparency is the design: /memories lists everything it knows and
/forget <id> deletes — a bot you can audit is a character, a bot that
keeps secret files is a problem. The harvester is instructed to skip
sensitive topics entirely.
"""
import html
import logging
import re
from collections import defaultdict, deque
from datetime import date

from telegram import Update
from telegram.error import TelegramError
from telegram.ext import CommandHandler, ContextTypes, MessageHandler, filters

import ai
import db
from .common import GROUP_TYPES, require_group

log = logging.getLogger("partybot.brain")

HARVEST_MIN_MESSAGES = 25   # new messages required before a harvest runs
HARVEST_DAILY_CAP = 6       # harvests per chat per day

_window: dict[int, deque] = defaultdict(lambda: deque(maxlen=60))
_fresh: dict[int, int] = defaultdict(int)          # messages since last harvest
_harvests: dict[int, tuple[str, int]] = {}         # chat -> (day, count)

# "remember when we..." is reminiscing, not an instruction — the guard
# below leaves those to the persona's judgment.
_REMEMBER_RE = re.compile(
    r"^(?:please\s+)?remember[,:\s]+(?!when\s)(.+)$", re.IGNORECASE | re.DOTALL
)
_FORGET_RE = re.compile(
    r"^(?:please\s+)?forget[,:\s]+(.+)$", re.IGNORECASE | re.DOTALL
)
MARKER_RE = re.compile(r"\[\[\s*remember\s*:\s*(.+?)\s*\]\]", re.IGNORECASE)


# ------------------------------------------------- instruction & marker API
# (used by handlers/persona.py)

def parse_instruction(text: str) -> tuple[str, str] | None:
    """('remember'|'forget', payload) when an addressed message is a direct
    memory instruction, else None."""
    text = text.strip()
    m = _REMEMBER_RE.match(text)
    if m:
        return "remember", m.group(1).strip()
    m = _FORGET_RE.match(text)
    if m:
        return "forget", m.group(1).strip()
    return None


def strip_markers(reply: str) -> tuple[str, list[str]]:
    """Remove [[remember: ...]] markers from a persona reply. Returns the
    clean reply and the facts (max 2, length-capped by db.add_memory)."""
    facts = MARKER_RE.findall(reply)[:2]
    clean = MARKER_RE.sub("", reply).strip()
    return clean, facts


def handle_instruction(chat_id: int, kind: str, payload: str) -> str:
    """Apply a direct instruction; returns the in-character confirmation."""
    if kind == "remember":
        saved = db.add_memory(chat_id, payload, "told")
        if saved is None:
            return "Already in the file. I never forgot it the first time."
        return "🧠 Noted, filed, and cross-referenced. I forget nothing."
    matches = db.find_memories(chat_id, payload)
    if not matches:
        return "Nothing in the file matches that — my conscience is clear."
    if len(matches) > 1:
        listed = "; ".join(f"#{m['id']} “{m['text'][:40]}”" for m in matches[:4])
        return (f"That matches {len(matches)} memories ({listed}…). "
                f"/forget <id> to pick one.")
    db.delete_memory(chat_id, matches[0]["id"])
    return f"🕳 Forgotten: “{matches[0]['text']}”. What were we talking about?"


# ------------------------------------------------------------------ commands

async def memories_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_group(update):
        return
    rows = db.memories_all(update.effective_chat.id)
    if not rows:
        await update.effective_message.reply_text(
            "🧠 The file is empty. Tell me things (“@%s remember …”) or "
            "just talk — I pick things up." % context.bot.username
        )
        return
    lines = ["🧠 <b>What I know</b> (/forget <i>id</i> to erase):"]
    for r in rows:
        tag = "🗣" if r["source"] == "told" else "👁"
        lines.append(f"  <b>#{r['id']}</b> {tag} {html.escape(r['text'])}")
    await update.effective_message.reply_html("\n".join(lines))


async def forget_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_group(update):
        return
    msg = update.effective_message
    arg = (context.args or [""])[0]
    if not arg.isdecimal():
        await msg.reply_text("Which memory? /forget <id> — ids are in /memories.")
        return
    if db.delete_memory(update.effective_chat.id, int(arg)):
        await msg.reply_text("🕳 Gone. I know nothing.")
    else:
        await msg.reply_text("No memory with that id — check /memories.")


# ----------------------------------------------------------------- harvester

async def observe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Group-5 observer: keep a rolling window of chat for the harvester."""
    chat = update.effective_chat
    msg = update.effective_message
    user = update.effective_user
    if (chat is None or chat.type not in GROUP_TYPES or msg is None
            or not msg.text or user is None or user.is_bot):
        return
    _window[chat.id].append(f"{user.first_name}: {msg.text[:200]}")
    _fresh[chat.id] += 1


async def _harvest_job(context: ContextTypes.DEFAULT_TYPE):
    if not ai.ENABLED:
        return
    today = date.today().isoformat()
    for chat_id, window in list(_window.items()):
        if _fresh[chat_id] < HARVEST_MIN_MESSAGES:
            continue
        day, n = _harvests.get(chat_id, (today, 0))
        if day == today and n >= HARVEST_DAILY_CAP:
            continue
        _fresh[chat_id] = 0
        _harvests[chat_id] = (today, n + 1 if day == today else 1)
        existing = [r["text"] for r in db.memories_all(chat_id)]
        try:
            facts = await ai.harvest_memories(chat_id, list(window), existing)
        except Exception:
            log.exception("harvest failed for chat %s", chat_id)
            continue
        for fact in facts:
            db.add_memory(chat_id, fact, "observed")
        if facts:
            log.info("harvested %d memories for chat %s", len(facts), chat_id)


def schedule(app) -> None:
    app.job_queue.run_repeating(
        _harvest_job, interval=7200, first=600, name="memory-harvest"
    )


def get_handlers():
    return [
        CommandHandler("memories", memories_cmd),
        CommandHandler("forget", forget_cmd),
        # Group 5: pure observer, never replies.
        (MessageHandler(
            filters.ChatType.GROUPS & filters.TEXT & ~filters.COMMAND, observe,
        ), 5),
    ]
