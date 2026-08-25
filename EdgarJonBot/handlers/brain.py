"""/remember, /brain, /forget — and the learning engine behind them.

Facts get in three ways: you tell the bot directly ("remember X" — deterministic,
no API needed), the bot learns on the spot from anything said to it (adding,
correcting or dropping facts as the conversation warrants), and a background
pass distills the chat every few messages. Standing instructions about the
bot's own behaviour ("be shorter") are kept as 'style' facts and obeyed.

/brain lists everything; /forget takes ids, words, "last" or "all"; or just say
"forget the postgres thing". Auditable memory is the whole point.
"""
import html
import logging
import re

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

import ai
import db
from .common import arg_text, fmt_when

log = logging.getLogger("edgarjon.brain")

_REMEMBER_RE = re.compile(r"^(?:please\s+)?remember[,:\s]+(?!when\s)(.+)$", re.IGNORECASE | re.DOTALL)
_FORGET_RE = re.compile(
    r"^(?:please\s+|can\s+you\s+|could\s+you\s+)*"
    r"(?:forget|erase|delete|wipe|scrub|drop|remove|unlearn|stop\s+remembering|don'?t\s+remember|never\s+mind)"
    r"((?:\s+(?:the|that|this|those|these|any|all|your|my))*)"
    r"(?:\s+(?:memories|memory|facts|fact|notes|note|things|thing|stuff|file|brain))?"
    r"(?:\s+(?:about|of|on|regarding|that\s+says|that\s+said))?"
    r"(?:\s+what\s+you\s+(?:know|remember|have)\s+(?:about|on))?"
    r"[,:\s]*(.*)$",
    re.IGNORECASE | re.DOTALL,
)
_ALL_RE = re.compile(
    r"^(?:everything|all|it\s+all|all\s+of\s+it|your\s+(?:whole\s+)?(?:memory|memories|file|brain|notebook)|"
    r"what\s+you\s+know|everything\s+you\s+know|literally\s+everything)(?:\s+about\s+(?:us|this\s+chat|everyone))?[.!\s]*$",
    re.IGNORECASE,
)
_LAST_RE = re.compile(
    r"^(?:what\s+i\s+(?:just\s+)?said|that\s+last\s+(?:thing|one|bit)|the\s+last\s+(?:thing|one|memory|fact)|"
    r"that(?:\s+one)?|it|the\s+latest(?:\s+one)?)[.!\s]*$", re.IGNORECASE)
_SCOPE_ALL_RE = re.compile(r"\b(?:all|everything|anything|every)\b", re.IGNORECASE)
_IDS_RE = re.compile(r"^(?:#?\d+(?:\s*(?:[,/&]|and|\s)\s*))*#?\d+$", re.IGNORECASE)
_STYLE_RE = re.compile(
    r"^(?:from\s+now\s+on|going\s+forward|in\s+future|always|never|stop|please\s+(?:always|never|stop))\b", re.IGNORECASE)


def parse_instruction(text: str) -> tuple[str, str] | None:
    """('remember'|'forget'|'forget_ids'|'forget_last'|'forget_all', payload) or None."""
    text = text.strip()
    m = _REMEMBER_RE.match(text)
    if m:
        return "remember", m.group(1).strip()
    m = _FORGET_RE.match(text)
    if m:
        fillers, payload = m.group(1).split(), m.group(2).strip().rstrip(".!?")
        if not payload and any(w.lower() in ("that", "this", "those", "these") for w in fillers):
            return "forget_last", ""
        if not payload or _ALL_RE.match(payload):
            return "forget_all", ""
        if _LAST_RE.match(payload):
            return "forget_last", ""
        if _IDS_RE.match(payload):
            return "forget_ids", " ".join(re.findall(r"\d+", payload))
        return "forget", payload
    return None


def _cb(user_id: int, action: str, arg: str = "") -> str:
    return f"mem:{user_id}:{action}:{arg}"


def handle_forget(chat_id: int, user_id: int, kind: str, payload: str):
    """Returns (text, keyboard|None)."""
    if kind == "forget_all":
        n = len(db.facts(chat_id, limit=10000))
        if n == 0:
            return "Nothing to forget. The notebook is blank.", None
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton(f"🕳 Yes, wipe all {n}", callback_data=_cb(user_id, "wipe")),
            InlineKeyboardButton("Keep them", callback_data=_cb(user_id, "keep")),
        ]])
        return f"Wipe all {n} facts, including your standing instructions? Tap to confirm.", kb
    if kind == "forget_last":
        last = db.latest_fact(chat_id)
        if last is None:
            return "Nothing to forget.", None
        db.delete_fact(chat_id, last["id"])
        return f"🕳 Forgotten: “{last['text']}”.", None
    if kind == "forget_ids":
        ids = [int(x) for x in payload.split()]
        rows = [r for r in db.facts(chat_id, limit=10000) if r["id"] in ids]
        n = db.delete_facts(chat_id, [r["id"] for r in rows])
        if n == 0:
            return "None of those ids are in /brain.", None
        missing = sorted(set(ids) - {r["id"] for r in rows})
        out = f"🕳 Forgotten {n}: " + "; ".join(f"“{r['text'][:40]}”" for r in rows)
        return out + (f" (no such id: {', '.join(map(str, missing))})" if missing else ""), None
    matches = db.find_facts(chat_id, payload)
    if not matches:
        return "Nothing in the notebook matches that.", None
    if len(matches) == 1:
        db.delete_fact(chat_id, matches[0]["id"])
        return f"🕳 Forgotten: “{matches[0]['text']}”.", None
    if _SCOPE_ALL_RE.search(payload):
        n = db.delete_facts(chat_id, [m["id"] for m in matches])
        return f"🕳 Forgotten all {n} of them.", None
    rows = [[InlineKeyboardButton(f"🕳 #{m['id']} {m['text'][:28]}", callback_data=_cb(user_id, "del", str(m["id"])))]
            for m in matches[:6]]
    rows.append([InlineKeyboardButton(f"All {min(len(matches), 6)} of these",
                                      callback_data=_cb(user_id, "dels", ",".join(str(m["id"]) for m in matches[:6])))])
    listed = "\n".join(f"  #{m['id']} {m['text'][:60]}" for m in matches[:6])
    more = f"\n  …and {len(matches) - 6} more" if len(matches) > 6 else ""
    return f"That matches {len(matches)}:\n{listed}{more}\nTap one, or say “forget all of them”.", InlineKeyboardMarkup(rows)


def handle_instruction(chat_id: int, user_id: int, kind: str, payload: str):
    """Deterministic path for direct instructions. Returns (text, keyboard|None)."""
    if kind == "remember":
        source = "style" if _STYLE_RE.match(payload) else "command"
        fid = db.add_fact(chat_id, payload, source)
        if fid is None:
            return "Already have that.", None
        return ("Noted — and I'll behave accordingly." if source == "style" else "Noted."), None
    return handle_forget(chat_id, user_id, kind, payload)


# ------------------------------------------------------------ AI learning

def apply_learning(chat_id: int, result: dict, source: str, by: str = "") -> tuple[int, int, int, int]:
    """Apply a learn() result. Returns (facts_added, replaced, removed, ideas_added)."""
    known = {r["id"] for r in db.facts(chat_id, limit=10000)}
    removed = sum(1 for i in result.get("remove", []) if i in known and db.delete_fact(chat_id, i))
    replaced = sum(1 for r in result.get("replace", []) if r["id"] in known and db.replace_fact(chat_id, r["id"], r["text"]))
    added = sum(1 for f in result.get("facts", []) if db.add_fact(chat_id, f, source) is not None)
    added += sum(1 for f in result.get("style", []) if db.add_fact(chat_id, f, "style") is not None)
    existing_ideas = {t.lower() for t in db.idea_texts(chat_id)}
    ideas = 0
    for idea in result.get("ideas", []):
        if idea.lower() not in existing_ideas:
            db.add_idea(chat_id, idea, by or "overheard", "overheard")
            ideas += 1
    return added, replaced, removed, ideas


async def learn_now(chat_id: int, speaker: str, text: str) -> None:
    """Immediate learning from a message addressed to the bot."""
    if not ai.ENABLED:
        return
    try:
        result = await ai.learn(chat_id, rows=db.recent_messages(chat_id, limit=12), speaker=speaker, text=text)
    except Exception:
        log.exception("learn_now failed")
        return
    if result:
        a, r, d, i = apply_learning(chat_id, result, "told", speaker)
        if a or r or d or i:
            log.info("learned in %s: +%d facts ~%d -%d, +%d ideas", chat_id, a, r, d, i)


# ------------------------------------------------------------------ commands

async def remember(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = arg_text(update)
    if not text:
        await update.effective_message.reply_text("Usage: /remember Edgar's Postgres thing lives on branch wip/pg")
        return
    out, _ = handle_instruction(update.effective_chat.id, update.effective_user.id, "remember", text)
    await update.effective_message.reply_text(out)


async def brain(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = db.facts(update.effective_chat.id, limit=60)
    if not rows:
        await update.effective_message.reply_text("Empty. Talk more.")
        return
    tags = {"command": "🗣", "told": "🗣", "overheard": "👁", "style": "⚙️"}
    style = [r for r in rows if r["source"] == "style"]
    rest = [r for r in rows if r["source"] != "style"]
    lines = ["🧠 <b>What I've got</b> (/forget <i>id</i>)"]
    if style:
        lines.append("<b>Standing instructions</b>")
        lines += [f"<b>#{r['id']}</b> ⚙️ {html.escape(r['text'])}" for r in style]
        lines.append("<b>Facts</b>")
    lines += [f"<b>#{r['id']}</b> {tags.get(r['source'], '•')} {html.escape(r['text'])} <i>({fmt_when(r['ts'])})</i>" for r in rest]
    await update.effective_message.reply_html("\n".join(lines))


async def forget(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id, user_id = update.effective_chat.id, update.effective_user.id
    args = context.args or []
    if not args:
        await update.effective_message.reply_text("/forget <id> · /forget <words> · /forget last · /forget all")
        return
    if len(args) == 1 and args[0].isdigit():
        ok = db.delete_fact(chat_id, int(args[0]))
        await update.effective_message.reply_text("Forgotten." if ok else "No such fact.")
        return
    kind, payload = parse_instruction("forget " + " ".join(args)) or ("forget", " ".join(args))
    text, kb = handle_forget(chat_id, user_id, kind, payload)
    await update.effective_message.reply_text(text, reply_markup=kb)


async def memory_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    _, owner, action, arg = q.data.split(":", 3)
    if q.from_user.id != int(owner):
        await q.answer("Not your call.")
        return
    chat_id = q.message.chat_id
    await q.answer()
    if action == "keep":
        await q.edit_message_text("Kept.")
    elif action == "wipe":
        await q.edit_message_text(f"🕳 {db.delete_all_facts(chat_id)} facts gone. Blank slate.")
    elif action == "del":
        await q.edit_message_text("🕳 Forgotten." if db.delete_fact(chat_id, int(arg)) else "Already gone.")
    elif action == "dels":
        await q.edit_message_text(f"🕳 {db.delete_facts(chat_id, [int(x) for x in arg.split(',') if x])} forgotten.")


def get_handlers():
    return [
        CommandHandler("remember", remember),
        CommandHandler("brain", brain),
        CommandHandler("forget", forget),
        CallbackQueryHandler(memory_callback, pattern=r"^mem:\d+:(wipe|keep|del|dels):"),
    ]
