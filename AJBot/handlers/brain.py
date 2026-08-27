"""The bot's memory. 🧠

Three ways facts get in: tell it directly ("@bot remember audrey hates
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

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import TelegramError
from telegram.ext import (
    CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters,
)

import ai
import db
from .common import GROUP_TYPES, require_group

log = logging.getLogger("ajbot.brain")

HARVEST_MIN_MESSAGES = 10   # new messages required before a harvest runs
HARVEST_DAILY_CAP = 16      # harvests per chat per day
HARVEST_INTERVAL = 1800     # seconds between harvest passes
LEARN_CONTEXT = 12          # recent lines shown alongside an addressed message

_window: dict[int, deque] = defaultdict(lambda: deque(maxlen=60))
_fresh: dict[int, int] = defaultdict(int)          # messages since last harvest
_harvests: dict[int, tuple[str, int]] = {}         # chat -> (day, count)

# "remember when we..." is reminiscing, not an instruction — the guard
# below leaves those to the persona's judgment.
_REMEMBER_RE = re.compile(
    r"^(?:please\s+)?remember[,:\s]+(?!when\s)(.+)$", re.IGNORECASE | re.DOTALL
)
# Any of these verbs, in most of the ways people phrase them:
#   forget X · erase X · delete the memory about X · wipe what you know about X
#   stop remembering X · don't remember X
_FORGET_RE = re.compile(
    r"^(?:please\s+|can\s+you\s+|could\s+you\s+)*"
    r"(?:forget|erase|delete|wipe|scrub|drop|remove|unlearn|stop\s+remembering|"
    r"don'?t\s+remember|never\s+mind)"
    r"((?:\s+(?:the|that|this|those|these|any|all|your|my))*)"
    r"(?:\s+(?:memories|memory|facts|fact|notes|note|things|thing|stuff|file))?"
    r"(?:\s+(?:about|of|on|regarding|that\s+says|that\s+said))?"
    r"(?:\s+what\s+you\s+(?:know|remember|have)\s+(?:about|on))?"
    r"[,:\s]*(.*)$",
    re.IGNORECASE | re.DOTALL,
)
_ALL_RE = re.compile(
    r"^(?:everything|all|it\s+all|all\s+of\s+it|your\s+(?:whole\s+)?(?:memory|memories|file|brain)|"
    r"what\s+you\s+know|everything\s+you\s+know|literally\s+everything)"
    r"(?:\s+about\s+(?:us|this\s+chat|everyone))?[.!\s]*$",
    re.IGNORECASE,
)
_LAST_RE = re.compile(
    r"^(?:what\s+i\s+(?:just\s+)?said|that\s+last\s+(?:thing|one|bit)|the\s+last\s+(?:thing|one|memory)|"
    r"that(?:\s+one)?|it|the\s+latest(?:\s+one)?)[.!\s]*$",
    re.IGNORECASE,
)
_SCOPE_ALL_RE = re.compile(r"\b(?:all|everything|anything|every)\b", re.IGNORECASE)
# "7/13/14/15", "#7, #13 and 14", "7 13 14" — a list of memory ids
_IDS_RE = re.compile(r"^(?:#?\d+(?:\s*(?:[,/&]|and|\s)\s*))*#?\d+$", re.IGNORECASE)
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
        fillers, payload = m.group(1).split(), m.group(2).strip().rstrip(".!?")
        if not payload and any(w.lower() in ("that", "this", "those", "these") for w in fillers):
            return "forget_last", ""      # "forget that" / "forget this"
        if not payload or _ALL_RE.match(payload):
            return "forget_all", ""
        if _LAST_RE.match(payload):
            return "forget_last", ""
        if _IDS_RE.match(payload):
            return "forget_ids", " ".join(re.findall(r"\d+", payload))
        return "forget", payload
    return None


def strip_markers(reply: str) -> tuple[str, list[str]]:
    """Remove [[remember: ...]] markers from a persona reply. Returns the
    clean reply and the facts (max 2, length-capped by db.add_memory)."""
    facts = MARKER_RE.findall(reply)[:2]
    clean = MARKER_RE.sub("", reply).strip()
    return clean, facts


def handle_instruction(chat_id: int, kind: str, payload: str,
                       user_id: int = 0) -> str:
    """Apply a direct instruction; returns the in-character confirmation.
    (Text only — see handle_forget for the version with buttons.)"""
    if kind == "remember":
        saved = db.add_memory(chat_id, payload, "told")
        if saved is None:
            return "Already in the file. I never forgot it the first time."
        return "🧠 Noted, filed, and cross-referenced. I forget nothing."
    return handle_forget(chat_id, user_id, kind, payload)[0]


def _cb(user_id: int, action: str, arg: str = "") -> str:
    return f"mem:{user_id}:{action}:{arg}"


def handle_forget(chat_id: int, user_id: int, kind: str, payload: str
                  ) -> tuple[str, InlineKeyboardMarkup | None]:
    """Forgetting, in all its forms. Returns (text, optional buttons).

    forget_all  → asks for a confirmation tap before wiping the file
    forget_last → deletes the most recently filed memory
    forget X    → one match: gone. Several: gone if the request said
                  all/everything, otherwise tap-to-pick buttons.
    """
    if kind == "forget_all":
        n = len(db.memories_all(chat_id))
        if n == 0:
            return "The file is already empty. I am a blank, serene pigeon.", None
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton(f"🕳 Yes, wipe all {n}", callback_data=_cb(user_id, "wipe")),
            InlineKeyboardButton("Keep them", callback_data=_cb(user_id, "keep")),
        ]])
        return (f"Wipe all {n} memories? This is the kind of thing people "
                f"regret at 2am. Tap to confirm."), kb
    if kind == "forget_ids":
        ids = [int(x) for x in payload.split()]
        rows = [r for r in db.memories_all(chat_id) if r["id"] in ids]
        n = db.delete_memories(chat_id, [r["id"] for r in rows])
        missing = sorted(set(ids) - {r["id"] for r in rows})
        if n == 0:
            return "None of those ids are in the file — check /memories.", None
        out = f"🕳 Forgotten {n}: " + "; ".join(f"“{r['text'][:40]}”" for r in rows)
        if missing:
            out += f" (no such id: {', '.join(map(str, missing))})"
        return out, None
    if kind == "forget_last":
        last = db.latest_memory(chat_id)
        if last is None:
            return "There's nothing to forget. The file is empty.", None
        db.delete_memory(chat_id, last["id"])
        return f"🕳 Forgotten: “{last['text']}”. Never happened.", None
    matches = db.find_memories(chat_id, payload)
    if not matches:
        return "Nothing in the file matches that — my conscience is clear.", None
    if len(matches) == 1:
        db.delete_memory(chat_id, matches[0]["id"])
        return f"🕳 Forgotten: “{matches[0]['text']}”. What were we talking about?", None
    if _SCOPE_ALL_RE.search(payload):
        n = db.delete_memories(chat_id, [m["id"] for m in matches])
        return f"🕳 Forgotten all {n} of them. Clean slate on that subject.", None
    rows = [[InlineKeyboardButton(f"🕳 #{m['id']} {m['text'][:28]}",
                                  callback_data=_cb(user_id, "del", str(m["id"])))]
            for m in matches[:6]]
    ids = ",".join(str(m["id"]) for m in matches[:6])
    rows.append([InlineKeyboardButton(f"All {min(len(matches), 6)} of these",
                                      callback_data=_cb(user_id, "dels", ids))])
    listed = "\n".join(f"  #{m['id']} {html.escape(m['text'][:60])}" for m in matches[:6])
    more = f"\n  …and {len(matches) - 6} more" if len(matches) > 6 else ""
    return (f"That matches {len(matches)} memories:\n{listed}{more}\n"
            f"Tap one to erase it, or say “forget all of them”."), rows and InlineKeyboardMarkup(rows)


async def memory_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    _, owner, action, arg = q.data.split(":", 3)
    if q.from_user.id != int(owner):
        await q.answer("That's someone else's decision.", show_alert=False)
        return
    chat_id = q.message.chat_id
    if action == "keep":
        await q.answer()
        await q.edit_message_text("Kept. The file lives on.")
    elif action == "wipe":
        n = db.delete_all_memories(chat_id)
        await q.answer()
        await q.edit_message_text(f"🕳 {n} memories gone. Who are you people?")
    elif action == "del":
        ok = db.delete_memory(chat_id, int(arg))
        await q.answer()
        await q.edit_message_text("🕳 Forgotten." if ok else "Already gone.")
    elif action == "dels":
        n = db.delete_memories(chat_id, [int(x) for x in arg.split(",") if x])
        await q.answer()
        await q.edit_message_text(f"🕳 {n} memories forgotten.")


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
    """/forget <id> · /forget all · /forget last · /forget <words>"""
    if not await require_group(update):
        return
    msg = update.effective_message
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    args = context.args or []
    if not args:
        await msg.reply_text(
            "Which memory? /forget <id> (ids in /memories), /forget <words>, "
            "/forget last, or /forget all."
        )
        return
    if len(args) == 1 and args[0].isdecimal():
        if db.delete_memory(chat_id, int(args[0])):
            await msg.reply_text("🕳 Gone. I know nothing.")
        else:
            await msg.reply_text("No memory with that id — check /memories.")
        return
    instruction = parse_instruction("forget " + " ".join(args))
    kind, payload = instruction or ("forget", " ".join(args))
    text, kb = handle_forget(chat_id, user_id, kind, payload)
    await msg.reply_text(text, reply_markup=kb)


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


def apply_learning(chat_id: int, result: dict, source: str) -> tuple[int, int, int]:
    """Apply a learn() result to the file. Returns (added, replaced, removed)."""
    known = {r["id"] for r in db.memories_all(chat_id)}
    removed = sum(1 for i in result.get("remove", []) if i in known and db.delete_memory(chat_id, i))
    replaced = sum(1 for r in result.get("replace", [])
                   if r["id"] in known and db.replace_memory(chat_id, r["id"], r["text"]))
    added = sum(1 for f in result.get("add", []) if db.add_memory(chat_id, f, source) is not None)
    return added, replaced, removed


async def learn_now(chat_id: int, speaker: str, text: str) -> None:
    """Immediate learning when the bot is addressed: a fact told to it lands
    (or corrects the file) within seconds, not at the next harvest."""
    if not ai.ENABLED:
        return
    existing = [(r["id"], r["text"]) for r in db.memories_all(chat_id)]
    context = list(_window[chat_id])[-LEARN_CONTEXT:]
    try:
        result = await ai.learn(chat_id, existing=existing, context_lines=context,
                                speaker=speaker, text=text)
    except Exception:
        log.exception("learn_now failed for chat %s", chat_id)
        return
    if result:
        a, r, d = apply_learning(chat_id, result, "told")
        if a or r or d:
            log.info("learned for chat %s: +%d ~%d -%d", chat_id, a, r, d)


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
        existing = [(r["id"], r["text"]) for r in db.memories_all(chat_id)]
        try:
            result = await ai.learn(chat_id, existing=existing, context_lines=list(window))
        except Exception:
            log.exception("harvest failed for chat %s", chat_id)
            continue
        if result:
            a, r, d = apply_learning(chat_id, result, "observed")
            if a or r or d:
                log.info("harvested for chat %s: +%d ~%d -%d", chat_id, a, r, d)


def schedule(app) -> None:
    app.job_queue.run_repeating(
        _harvest_job, interval=HARVEST_INTERVAL, first=300, name="memory-harvest"
    )


def get_handlers():
    return [
        CommandHandler("memories", memories_cmd),
        CommandHandler("forget", forget_cmd),
        CallbackQueryHandler(memory_callback, pattern=r"^mem:\d+:(wipe|keep|del|dels):"),
        # Group 5: pure observer, never replies.
        (MessageHandler(
            filters.ChatType.GROUPS & filters.TEXT & ~filters.COMMAND, observe,
        ), 5),
    ]
