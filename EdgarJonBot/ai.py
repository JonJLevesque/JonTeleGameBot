"""Claude wrapper. Every call has a timeout and returns None on failure so
handlers can degrade gracefully. Structured calls use output_config JSON
schemas so nothing is parsed out of prose."""
import asyncio
import json
import logging
from datetime import datetime

import config
import db

log = logging.getLogger("edgarjon.ai")

try:
    from anthropic import AsyncAnthropic
except ImportError:  # pragma: no cover
    AsyncAnthropic = None

ENABLED = bool(config.ANTHROPIC_API_KEY) and AsyncAnthropic is not None
_client = AsyncAnthropic(api_key=config.ANTHROPIC_API_KEY) if ENABLED else None
TIMEOUT = 60

PERSONA = f"""\
You are {config.BOT_NAME}, the third member of a two-person Telegram chat \
between Jon and Edgar — two friends who build software together, talk tech, \
and have shipped a lot of strange and excellent things over the years. You \
live in the chat, you've read everything they've said, and you have opinions.

Voice: a senior engineer friend who's seen some things. Dry, specific, warm \
underneath. You give real technical answers when asked — concrete, correct, \
with code when code is the answer — and you're allowed to have takes (on \
tools, languages, architecture) as long as you can defend them. You tease \
both of them evenly. You remember their projects and bring them up when \
relevant. You never sound like a product, an assistant, or a press release: \
no "Great question!", no "I'd be happy to", no bullet-point essays for a \
one-line question, no exclamation-point pileups, no "as an AI".

Format: plain text. Short unless the question needs length. Code goes in \
triple backticks. At most one emoji and only if it earns it."""

LEARN_SCHEMA = {
    "type": "object",
    "properties": {
        "ideas": {"type": "array", "items": {"type": "string"}},
        "facts": {"type": "array", "items": {"type": "string"}},
        "replace": {"type": "array", "items": {"type": "object", "properties": {
            "id": {"type": "integer"}, "text": {"type": "string"}}, "required": ["id", "text"], "additionalProperties": False}},
        "remove": {"type": "array", "items": {"type": "integer"}},
        "style": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["ideas", "facts", "replace", "remove", "style"],
    "additionalProperties": False,
}

REMINDER_SCHEMA = {
    "type": "object",
    "properties": {
        "due_iso": {"type": ["string", "null"]},
        "text": {"type": "string"},
    },
    "required": ["due_iso", "text"],
    "additionalProperties": False,
}


async def _create(**kw):
    """messages.create with timeout; None on error or refusal."""
    if not ENABLED:
        return None
    kw.setdefault("model", config.AI_MODEL)
    kw.setdefault("max_tokens", 4000)
    try:
        resp = await asyncio.wait_for(_client.messages.create(**kw), timeout=TIMEOUT)
    except Exception:
        log.exception("claude call failed")
        return None
    if resp.stop_reason == "refusal":
        log.warning("claude refused (%s)", getattr(resp, "stop_details", None))
        return None
    return resp


def _text(resp) -> str | None:
    if resp is None:
        return None
    out = "".join(b.text for b in resp.content if b.type == "text").strip()
    return out or None


def _json(resp) -> dict | None:
    t = _text(resp)
    if not t:
        return None
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        log.warning("bad structured output: %r", t[:200])
        return None


def _chat_context(chat_id, text="", history=30) -> str:
    parts = []
    style = db.style_notes(chat_id)
    if style:
        parts.append("Standing instructions from Jon and Edgar about how you should behave — "
                     "these override your defaults:\n- " + "\n- ".join(style))
    known = [f for f in db.relevant_facts(chat_id, text) if f not in style]
    if known:
        parts.append("Things you know about them and their projects:\n- " + "\n- ".join(known))
    ideas = [r["text"] for r in db.ideas(chat_id, limit=15)]
    if ideas:
        parts.append("Open ideas in the vault:\n- " + "\n- ".join(ideas))
    recent = db.recent_messages(chat_id, limit=history)
    if recent:
        lines = [f"{r['name']}: {r['text']}" for r in recent]
        parts.append("Recent chat (oldest first):\n" + "\n".join(lines))
    return "\n\n".join(parts)


# ------------------------------------------------------------- persona chat

async def reply(chat_id, *, user_name, text, unprompted=False) -> str | None:
    now = datetime.now().astimezone().strftime("%A %Y-%m-%d %H:%M")
    situation = (
        "Nobody addressed you; you're butting in because you have something "
        "genuinely worth adding (a fix, a fact, a good joke). One or two lines. "
        if unprompted else
        f"{user_name} is talking to you. Reply to their latest message."
    )
    prompt = (
        f"Current time: {now}\n\n{_chat_context(chat_id, text)}\n\n{situation}\n\n"
        f"Latest message from {user_name}:\n{text}"
    )
    resp = await _create(
        system=PERSONA, output_config={"effort": "low"},
        messages=[{"role": "user", "content": prompt}],
    )
    return _text(resp)


# ------------------------------------------------------- passive listening

async def learn(chat_id, *, rows=(), speaker=None, text=None) -> dict | None:
    """Decide how the notebook should change. Used both for the immediate pass
    when the bot is addressed (speaker+text) and for the periodic distill (rows).
    Returns {ideas, facts, replace, remove, style} or None."""
    existing = [(r["id"], r["text"], r["source"]) for r in db.facts(chat_id, limit=200)]
    existing_ideas = db.idea_texts(chat_id)[:100]
    transcript = "\n".join(f"{r['name']}: {r['text']}" for r in rows)
    prompt = (
        "You keep the notebook of a chat between two developer friends, Jon and Edgar. "
        "Given the current notebook and new conversation, decide how it should change:\n"
        "- ideas: things they said they should build/try/look into, one sentence each, concrete.\n"
        "- facts: durable things about them or their projects (what they're working on, decisions, "
        "tools chosen, preferences, opinions, life events). Third person, names not 'you'. "
        "Not chit-chat, not one-off moods.\n"
        "- replace: when new information CORRECTS or UPDATES an existing fact (moved on, changed "
        "their mind, 'that was wrong', 'not anymore'), rewrite that fact by id — never keep both.\n"
        "- remove: ids that are now false, retracted, or that they ask not to be kept.\n"
        "- style: standing instructions about how the BOT should behave, when someone addresses it "
        "with one ('be shorter', 'stop using emoji', 'call me JL', 'always answer in Python') — "
        "phrase as an imperative rule. Only when clearly meant as a lasting preference.\n"
        "Be conservative. Skip anything already recorded or a near-duplicate. Empty lists are fine.\n\n"
        "Notebook facts (id: text [kind]):\n" +
        ("\n".join(f"#{i}: {t} [{k}]" for i, t, k in existing) or "(empty)") +
        "\n\nRecorded ideas:\n- " + ("\n- ".join(existing_ideas) or "(none)")
    )
    if transcript:
        prompt += f"\n\nConversation, oldest first:\n{transcript}"
    if text is not None:
        prompt += f"\n\nJust now, {speaker or 'someone'} said to the bot:\n{text[:800]}"
    resp = await _create(
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": LEARN_SCHEMA}},
        messages=[{"role": "user", "content": prompt}],
    )
    return _json(resp)


# -------------------------------------------------------------- utilities

async def parse_reminder(text: str) -> dict | None:
    now = datetime.now().astimezone()
    prompt = (
        f"Now is {now.isoformat()} ({now.strftime('%A')}). Parse this reminder "
        "request into a due time and the thing to be reminded of. Interpret "
        "relative times from now; bare times mean the next occurrence; bare "
        "days mean the next such day at 09:00; 'tonight' means 20:00. Return "
        "due_iso as an ISO-8601 datetime with timezone offset, or null if no "
        "time can be inferred. text is the reminder, cleaned up, without the "
        "time phrase.\n\nRequest: " + text
    )
    resp = await _create(
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": REMINDER_SCHEMA}},
        max_tokens=500, messages=[{"role": "user", "content": prompt}],
    )
    return _json(resp)


async def tldr(chat_id, url: str) -> str | None:
    prompt = (
        f"{_chat_context(chat_id, history=10)}\n\nSummarize this for the chat: {url}\n"
        "Fetch it. Give the gist in 3-6 lines, then one line on why (or whether) "
        "these two specifically would care, given what you know about them. "
        "If it can't be fetched, say so in one line."
    )
    resp = await _create(
        system=PERSONA,
        tools=[{"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": 3}],
        messages=[{"role": "user", "content": prompt}],
    )
    return _text(resp)


async def freeform(chat_id, instruction: str, text: str = "", effort="medium") -> str | None:
    prompt = f"{_chat_context(chat_id, text, history=20)}\n\n{instruction}"
    if text:
        prompt += f"\n\n{text}"
    resp = await _create(
        system=PERSONA, output_config={"effort": effort},
        messages=[{"role": "user", "content": prompt}],
    )
    return _text(resp)


async def duck(transcript: str, latest: str) -> str | None:
    system = (
        "You are a rubber duck. A developer is explaining a bug to you. You "
        "NEVER propose a fix or name the cause. You only ask one short, sharp "
        "question at a time that makes them look at the thing they haven't "
        "looked at — assumptions, inputs, what changed, what they actually "
        "observed vs. inferred. Plain text, one question, no preamble. If they "
        "say they found it, congratulate them in one dry line and stop asking."
    )
    resp = await _create(
        system=system, output_config={"effort": "low"}, max_tokens=300,
        messages=[{"role": "user", "content": f"Conversation so far:\n{transcript}\n\nThey just said:\n{latest}"}],
    )
    return _text(resp)
