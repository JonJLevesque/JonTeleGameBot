"""/pet — the chat's shared tamagotchi. 🐣

One pet per chat, co-parented and fed with cookies. Decay is LAZY: the
state stores last_tick and every command fast-forwards the elapsed time,
so the pet is always current without a per-minute job. The hourly keeper
job exists only to speak up proactively — a daily hunger warning, and the
tragic departure of a pet left starving (hunger pinned at 100) for 48
hours. It never dies; it packs a tiny bindle and runs away, and the chat
can adopt again once their hearts heal.
"""
import html
import random
import time as _time
from collections import defaultdict, deque
from datetime import datetime

from telegram import Update
from telegram.constants import ChatAction
from telegram.error import TelegramError
from telegram.ext import CommandHandler, ContextTypes

import ai
import db
from .common import LOCAL_TZ, require_group

SPECIES = ["🐱", "🐶", "🐢", "🦊", "🐸", "🐙", "🦔", "🐧", "🐰", "🦆"]

HUNGER_PER_HOUR = 2.5    # rises toward 100 (starving)
HAPPY_PER_HOUR = 1.5     # falls toward 0 (despondent)
FEED_HUNGER = 30
FEED_HAPPY = 5
REFUSE_BELOW = 10        # hunger under this: the pet refuses food
PLAY_HAPPY = 15
PLAY_HUNGER = 5          # exercise works up an appetite
PLAY_COOLDOWN = 30 * 60
GIFT_CHANCE = 0.05
WARN_AT = 80
RUNAWAY_AFTER = 48 * 3600
TALK_HAPPY = 2
TALK_BOOST_COOLDOWN = 10 * 60  # a monologue can't substitute for playtime

_PLAY_SCENES = [
    "{name} does a lap of honor around an imaginary track. Magnificent.",
    "{name} chases a bottle cap with the intensity of a championship final.",
    "{name} performs a trick nobody taught it. Nobody applauds harder than {name}.",
    "{name} hides, waits, pounces. You never stood a chance.",
    "{name} zooms. The zoomies cannot be explained, only witnessed.",
]

_GIFT_SCENES = [
    "While rummaging, {name} unearths something for you: +2 🍪!",
    "{name} proudly drops a find at your feet: +2 🍪. Do not ask where it was.",
    "{name} has been saving these for a special occasion. Apparently that's now: +2 🍪!",
]

# An egg can't talk back yet — but it can absolutely hear you.
_EGG_SCENES = [
    "The egg wobbles once, then goes very still. Something in there is listening.",
    "A faint tap-tap answers from inside the shell. Message received.",
    "The egg tilts toward your voice and settles, somehow smug about it.",
    "Nothing. Then, just as you turn away — one decisive thump.",
    "The egg rocks gently, warmed by the attention. It can't talk yet. It will remember this.",
]

# When the AI is unavailable (or bails), the pet still acknowledges you.
_TALK_FALLBACK = [
    "{name} tilts its head at exactly the wrong angle and blinks twice. Understood, probably.",
    "{name} listens with its whole body, then answers with a small noise that means everything and nothing.",
    "{name} stares deep into your soul, then grooms its own shoulder. Conversation complete.",
    "{name} nods along like an old friend who wasn't listening but loves you anyway.",
    "{name} presses against your leg. Whatever you said, the answer is yes.",
]

# Recent /pet talk exchanges per chat, so the pet keeps a thread of the
# conversation. In-memory on purpose: a restart forgetting small talk is
# exactly how pets work.
_talk_context: dict[int, deque] = defaultdict(lambda: deque(maxlen=10))


# ------------------------------------------------------------ pure pet logic

def new_pet(name: str, now: float, species: str | None = None) -> dict:
    return {
        "name": name,
        "species": species or random.choice(SPECIES),
        "born": now,
        "hunger": 0.0,
        "happiness": 80.0,
        "last_tick": now,
        "warned_day": None,
        "starved_since": None,
        "fed_by": {},
    }


def _update_starvation(state: dict, now: float,
                       overshoot_hours: float = 0.0) -> None:
    """Track the moment hunger first pinned at 100. When a lazy tick jumps
    past 100 mid-interval, back-date starved_since to the crossing point so
    a long absence can't reset the 48h runaway clock."""
    if state["hunger"] >= 100:
        if not state.get("starved_since"):
            state["starved_since"] = now - overshoot_hours * 3600
    else:
        state["starved_since"] = None


def tick(state: dict, now: float) -> dict:
    """Fast-forward decay from last_tick to now (fractional hours exact)."""
    hours = max(0.0, now - state["last_tick"]) / 3600
    raw = state["hunger"] + HUNGER_PER_HOUR * hours
    state["hunger"] = min(100.0, raw)
    state["happiness"] = max(0.0, state["happiness"] - HAPPY_PER_HOUR * hours)
    state["last_tick"] = now
    overshoot = max(0.0, raw - 100.0) / HUNGER_PER_HOUR
    _update_starvation(state, now, overshoot_hours=overshoot)
    return state


def has_run_away(state: dict, now: float) -> bool:
    since = state.get("starved_since")
    return since is not None and now - since >= RUNAWAY_AFTER


def stage_of(state: dict, now: float) -> tuple[str, str]:
    """(label, emoji) — the egg hasn't hatched into its species yet."""
    age = now - state["born"]
    if age < 86400:
        return "egg", "🥚"
    if age < 7 * 86400:
        return "baby", state["species"]
    if age < 30 * 86400:
        return "teen", state["species"]
    return "adult", state["species"]


def feed(state: dict, user_id: int, user_name: str, now: float) -> str:
    """Apply a feeding (state already ticked). 'refused' means no cookie
    should be charged."""
    if state["hunger"] < REFUSE_BELOW:
        return "refused"
    state["hunger"] = max(0.0, state["hunger"] - FEED_HUNGER)
    state["happiness"] = min(100.0, state["happiness"] + FEED_HAPPY)
    _update_starvation(state, now)
    parent = state["fed_by"].setdefault(str(user_id), {"name": user_name, "count": 0})
    parent["name"] = user_name
    parent["count"] += 1
    return "ok"


def play_wait(state: dict, now: float) -> float:
    """Seconds until the pet wants to play again (0 = ready now)."""
    last = state.get("last_play")
    return max(0.0, last + PLAY_COOLDOWN - now) if last else 0.0


def play(state: dict, now: float) -> str:
    if play_wait(state, now) > 0:
        return "cooldown"
    state["happiness"] = min(100.0, state["happiness"] + PLAY_HAPPY)
    state["hunger"] = min(100.0, state["hunger"] + PLAY_HUNGER)
    state["last_play"] = now
    _update_starvation(state, now)
    return "ok"


def talk_boost(state: dict, now: float) -> bool:
    """Being spoken to warms the pet — a small happiness bump, at most once
    per TALK_BOOST_COOLDOWN. The pet always answers; only the bump is gated."""
    last = state.get("last_talk_boost")
    if last is not None and now - last < TALK_BOOST_COOLDOWN:
        return False
    state["happiness"] = min(100.0, state["happiness"] + TALK_HAPPY)
    state["last_talk_boost"] = now
    return True


def bar(value: float) -> str:
    n = round(min(100.0, max(0.0, value)) / 10)
    return "█" * n + "░" * (10 - n)


def hunger_mood(h: float) -> str:
    if h < 10:
        return "stuffed"
    if h < 35:
        return "content"
    if h < 60:
        return "peckish"
    if h < WARN_AT:
        return "hungry"
    return "STARVING"


def happiness_mood(hp: float) -> str:
    if hp >= 85:
        return "elated"
    if hp >= 60:
        return "happy"
    if hp >= 40:
        return "fine"
    if hp >= 15:
        return "mopey"
    return "despondent"


def status_card(state: dict, now: float) -> str:
    label, emoji = stage_of(state, now)
    name = html.escape(state["name"])
    days = int((now - state["born"]) // 86400)
    age = "not hatched yet" if label == "egg" else (
        f"{days} day{'s' if days != 1 else ''} old"
    )
    lines = [
        f"{emoji} <b>{name}</b> — {label}, {age}",
        f"<code>Hunger:    {bar(state['hunger'])}</code> {hunger_mood(state['hunger'])}",
        f"<code>Happiness: {bar(state['happiness'])}</code> {happiness_mood(state['happiness'])}",
    ]
    if state["fed_by"]:
        top = max(state["fed_by"].values(), key=lambda p: p["count"])
        lines.append(
            f"Top parent: {html.escape(top['name'])} "
            f"({top['count']} feeding{'s' if top['count'] != 1 else ''})"
        )
    if state["hunger"] >= WARN_AT:
        lines.append(f"😿 {name} needs food badly — /pet feed (1 🍪)")
    return "\n".join(lines)


def _farewell(name: str) -> str:
    safe = html.escape(name)
    return (
        f"🧳 <b>{safe} has run away.</b>\n\n"
        f"Sometime in the night, {safe} packed a tiny bindle and slipped "
        f"out the window. The note reads: “i waited. the bowl stayed "
        f"empty. i still love you. don't look for me.”\n\n"
        f"(/pet adopt — when your hearts have healed.)"
    )


# ------------------------------------------------------------------ handlers

def _load(chat_id: int, now: float) -> dict | None:
    """Current (ticked) pet state, persisted so decay survives quiet spells."""
    state = db.get_pet(chat_id)
    if state is None:
        return None
    tick(state, now)
    db.save_pet(chat_id, state)
    return state


async def _maybe_gift(msg, actor, chat_id: int, name: str) -> None:
    if random.random() < GIFT_CHANCE:
        db.add_cookies(chat_id, actor.id, 2, "pet gift")
        scene = random.choice(_GIFT_SCENES).format(name=html.escape(name))
        await msg.reply_html(f"✨ {scene}")


async def pet_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_group(update):
        return
    msg = update.effective_message
    chat_id = update.effective_chat.id
    user = update.effective_user
    now = _time.time()
    args = context.args or []
    sub = args[0].lower() if args else ""

    if sub == "adopt":
        if db.get_pet(chat_id) is not None:
            state = _load(chat_id, now)
            await msg.reply_html(
                "One family, one pet — you already have:\n\n"
                + status_card(state, now)
            )
            return
        name = " ".join(args[1:]).strip()
        if not name or len(name) > 20:
            await msg.reply_text(
                "Name your new family member: /pet adopt <name> "
                "(20 characters max — it has to fit on the tiny collar)."
            )
            return
        state = new_pet(name, now)
        db.save_pet(chat_id, state)
        await msg.reply_html(
            f"🥚 <b>An egg has appeared!</b> Inside: <b>{html.escape(name)}</b>, "
            f"who already loves you unconditionally and expects the same.\n"
            f"It hatches in a day. Keep it fed (/pet feed, 1 🍪), "
            f"entertained (/pet play) and talked to (/pet talk hi — it "
            f"talks back once hatched). A pet left starving too long "
            f"<i>will</i> pack its bags."
        )
        return

    state = _load(chat_id, now)
    if state is None:
        await msg.reply_text(
            "This chat has no pet yet! /pet adopt <name> — a mystery egg, "
            "co-parented by everyone, fed with cookies. What could go wrong?"
        )
        return
    if has_run_away(state, now):
        db.clear_pet(chat_id)
        await msg.reply_html(_farewell(state["name"]))
        return

    name = state["name"]
    safe = html.escape(name)

    if sub in ("", "status"):
        await msg.reply_html(status_card(state, now))
    elif sub == "feed":
        result = feed(state, user.id, user.first_name, now)
        if result == "refused":
            db.save_pet(chat_id, state)
            await msg.reply_html(
                f"{safe} is stuffed and looks at you with betrayal. "
                f"(No 🍪 spent.)"
            )
            return
        if db.get_cookies(chat_id, user.id) < 1:
            await msg.reply_text(
                f"Feeding costs 1 🍪 and you're broke. {name} pretends "
                f"not to notice, which is worse."
            )
            return
        db.add_cookies(chat_id, user.id, -1, "pet food")
        db.save_pet(chat_id, state)
        await msg.reply_html(
            f"🍽️ {safe} devours the cookie "
            f"({hunger_mood(state['hunger'])} now). "
            f"Somewhere, a tiny heart grows fonder of you specifically."
        )
        await _maybe_gift(msg, user, chat_id, name)
    elif sub == "play":
        result = play(state, now)
        db.save_pet(chat_id, state)
        if result == "cooldown":
            mins = int(play_wait(state, now) // 60) + 1
            await msg.reply_html(
                f"{safe} is napping dramatically — try again in ~{mins} min."
            )
            return
        scene = random.choice(_PLAY_SCENES).format(name=safe)
        await msg.reply_html(f"🎾 {scene}")
        await _maybe_gift(msg, user, chat_id, name)
    elif sub == "talk":
        text = " ".join(args[1:]).strip()
        if not text:
            await msg.reply_text(
                f"/pet talk <message> — say it out loud; {name} is listening."
            )
            return
        talk_boost(state, now)
        db.save_pet(chat_id, state)
        label, emoji = stage_of(state, now)
        if label == "egg":
            await msg.reply_html("🥚 " + random.choice(_EGG_SCENES))
            return
        lines = _talk_context[chat_id]
        lines.append(f"{user.first_name}: {text[:200]}")
        reply = None
        if ai.ENABLED:
            await context.bot.send_chat_action(chat_id, ChatAction.TYPING)
            reply = await ai.pet_reply(
                chat_id,
                name=name,
                species=state["species"],
                stage=label,
                hunger=hunger_mood(state["hunger"]),
                happiness=happiness_mood(state["happiness"]),
                user_name=user.first_name,
                text=text[:400],
                context_lines=list(lines),
            )
        if not reply:
            reply = random.choice(_TALK_FALLBACK).format(name=name)
        lines.append(f"{name}: {reply[:200]}")
        await msg.reply_text(f"{emoji} {reply}")
    elif sub == "rename":
        new_name = " ".join(args[1:]).strip()
        if not new_name or len(new_name) > 20:
            await msg.reply_text("/pet rename <name> (20 characters max).")
            return
        state["name"] = new_name
        db.save_pet(chat_id, state)
        await msg.reply_html(
            f"{safe} is now <b>{html.escape(new_name)}</b>, and will spend "
            f"the afternoon not answering to either name."
        )
    else:
        await msg.reply_text(
            "/pet — status · /pet adopt <name> · /pet feed (1 🍪) · "
            "/pet play · /pet talk <message> · /pet rename <name>"
        )


# ---------------------------------------------------------------- keeper job

async def _keeper_job(context: ContextTypes.DEFAULT_TYPE):
    """Hourly: warn about starving pets (once a day) and let a pet that has
    starved for 48h run away. Lazy ticks keep the numbers honest between runs."""
    now = _time.time()
    today = datetime.now(LOCAL_TZ).date().isoformat()
    for chat_id, state in db.all_pets():
        tick(state, now)
        if has_run_away(state, now):
            db.clear_pet(chat_id)
            try:
                await context.bot.send_message(
                    chat_id, _farewell(state["name"]), parse_mode="HTML"
                )
            except TelegramError:
                pass
            continue
        warn = state["hunger"] >= WARN_AT and state.get("warned_day") != today
        if warn:
            state["warned_day"] = today
        db.save_pet(chat_id, state)
        if warn:
            try:
                await context.bot.send_message(
                    chat_id,
                    f"😿 {html.escape(state['name'])} is starving — "
                    f"/pet feed (1 🍪). The bindle is being eyed.",
                    parse_mode="HTML",
                )
            except TelegramError:
                pass


def schedule(app) -> None:
    app.job_queue.run_repeating(
        _keeper_job, interval=3600, first=120, name="pet-keeper"
    )


def get_handlers():
    return [CommandHandler("pet", pet_cmd)]
