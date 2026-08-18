"""Optional AI prompt generation via the Claude API.

When ANTHROPIC_API_KEY is set, party-game prompts are generated fresh per
request (so they never repeat or run out) instead of drawn from the static
banks in prompts.py. Every call has a hard timeout and falls back to the
static banks on any failure, refusal, or missing key — the bot never blocks
on the API.

A short per-chat history of recent prompts is kept in memory and passed to
the model so consecutive rounds don't converge on the same ideas.
"""
import asyncio
import logging
from collections import defaultdict, deque

import config

log = logging.getLogger("partybot.ai")

try:
    from anthropic import AsyncAnthropic
except ImportError:
    AsyncAnthropic = None

ENABLED = bool(config.ANTHROPIC_API_KEY) and AsyncAnthropic is not None
_client = AsyncAnthropic(api_key=config.ANTHROPIC_API_KEY) if ENABLED else None

TIMEOUT_SECONDS = 15
_recent: dict[tuple[int, str], deque] = defaultdict(lambda: deque(maxlen=10))

SYSTEM = """\
You write prompts for a party-game bot in a Telegram chat. Your entire reply is \
sent to the chat verbatim as the game prompt, so output ONLY the prompt itself — \
no preamble, no quotation marks around it, no commentary.

Voice: the funniest, sharpest friend in the group chat — dry, specific, a little \
too observant. Never a party-game app. Concretely that means: no exclamation-point \
pileups, no "the group will judge you!", no forced wackiness, no clichés like \
"spill the tea", no hedging. Specific beats generic; bold beats cute; one clean \
sentence beats three. A great prompt makes someone say "oh no" and then answer \
anyway.

Hard rules:
- Any prompt involving people must be about members of THIS chat. Never outside \
crushes, exes, partners, contacts, or celebrities.
- Dares must be doable inside Telegram: text, voice message, photo, profile \
picture, DM to a chat member. Nothing requiring people to be in the same room.
- Plain text only. No markdown, no emoji unless one genuinely lands."""

CATEGORY_INSTRUCTIONS = {
    "truth": (
        "Write one truth question. It should be genuinely revealing or genuinely "
        "funny — a question people actually want to hear answered, not therapy "
        "boilerplate like 'what's your biggest fear'."
    ),
    "dare": (
        "Write one dare, executable entirely inside Telegram. It should be "
        "slightly embarrassing in a fun way, never humiliating, and specific "
        "enough that there's no wriggle room."
    ),
    "wyr": (
        "Write one 'Would you rather' dilemma where both options are genuinely "
        "hard to pick between. No obvious right answer."
    ),
    "paranoia": (
        "Write one Paranoia question — it will be shown secretly to one player, "
        "who answers it out loud while the chat doesn't know the question. Either "
        "a 'who in this chat...' question they answer with a name, or a pointed "
        "yes/no question about the named subject. The fun is that the answer is "
        "intriguing without the question. Hard limit: 150 characters (it's shown "
        "in a small popup)."
    ),
    "dailyq": (
        "Write one 'daily question' for the chat's question-of-the-day ritual — "
        "a single open question both people answer. The arc matters: match the "
        "intimacy stage given in the context, never colder, at most a half-step "
        "warmer. One sentence, no preamble."
    ),
    "roleplay": (
        "Write a roleplay setup: one scenario (1-2 sentences, a situation with "
        "built-in tension or absurdity) and one role per listed player. The roles "
        "should rub against each other — conflict or chemistry, not four random "
        "hats. Format exactly:\n"
        "<scenario>\n"
        "• <player name> — <their role>\n"
        "(one bullet per player, nothing after the last bullet)"
    ),
}


def _context_lines(*, duo, spicy, user_name, subject, names):
    lines = []
    if duo:
        other = subject or "the other person"
        lines.append(
            f"The chat has exactly two people: {user_name} (who receives this "
            f"prompt) and {other}. Make it about the two of them — 'who in this "
            f"chat' questions are pointless here, and never say 'the group'."
        )
    else:
        lines.append(
            f"This is a group chat. The prompt is for {user_name}."
            + (f" If the prompt needs a specific other person, use {subject}." if subject else "")
        )
    if names:
        lines.append("Players to cast, in order: " + ", ".join(names) + ".")
    if spicy:
        lines.append(
            "Spicy mode is on and everyone is an adult: flirty and bold is good, "
            "tension is good. Suggestive, never explicit."
        )
    else:
        lines.append("Keep it fully family-friendly.")
    return lines


async def generate(category, chat_id, *, duo=False, spicy=False,
                   user_name="the player", subject=None, names=None, extra=None):
    """Return a fresh prompt string, or None (caller falls back to static)."""
    if not ENABLED:
        return None
    key = (chat_id, category)
    parts = [CATEGORY_INSTRUCTIONS[category]]
    parts += _context_lines(duo=duo, spicy=spicy, user_name=user_name,
                            subject=subject, names=names)
    if spicy and category == "roleplay":
        parts.append(
            "Spicy roleplay in this chat means one specific flavor: build the "
            "scenario around a playful daddy/babygirl power dynamic between "
            "the first two players. One role gets the daddy energy — calm, in "
            "charge, caretaker-with-an-edge, says things like “careful” and "
            "“come here” as complete sentences. The other gets the babygirl "
            "energy — sweet, bratty, testing the rules on purpose, losing on "
            "purpose. Use the words daddy/babygirl when they land naturally. "
            "Decide freely which player gets which role (vary it). Charged "
            "and suggestive, never explicit."
        )
    if extra:
        parts.append(extra)
    if _recent[key]:
        parts.append(
            "Recently used in this chat (do something clearly different):\n- "
            + "\n- ".join(_recent[key])
        )
    # Opus-5-tier models think by default (needs max_tokens headroom) and
    # support effort + server-side refusal fallbacks; smaller/older models
    # (e.g. claude-haiku-4-5, the cheap default) reject those parameters.
    if config.AI_MODEL.startswith(("claude-opus-5", "claude-fable-5", "claude-mythos-5")):
        request = _client.beta.messages.create(
            model=config.AI_MODEL,
            max_tokens=2000,
            output_config={"effort": "low"},
            betas=["server-side-fallback-2026-06-01"],
            fallbacks=[{"model": "claude-opus-4-8"}],
            system=SYSTEM,
            messages=[{"role": "user", "content": "\n\n".join(parts)}],
        )
    else:
        request = _client.messages.create(
            model=config.AI_MODEL,
            max_tokens=500,
            system=SYSTEM,
            messages=[{"role": "user", "content": "\n\n".join(parts)}],
        )
    try:
        response = await asyncio.wait_for(request, timeout=TIMEOUT_SECONDS)
        if response.stop_reason == "refusal":
            log.warning("AI prompt generation refused (category=%s)", category)
            return None
        text = "".join(
            block.text for block in response.content if block.type == "text"
        ).strip()
        if not text:
            return None
        _recent[key].append(text[:120])
        return text
    except Exception:
        log.exception("AI prompt generation failed (category=%s)", category)
        return None
