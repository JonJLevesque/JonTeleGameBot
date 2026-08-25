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

SPECIES = ["🐱", "🐶", "🐢", "🦊", "🐸", "🐙", "🦔", "🐧", "🐰", "🦆", "🦢"]

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
ADORE_HAPPY = 8
ADORE_COOLDOWN = 20 * 60       # per person — affection is not a slot machine
TRAIN_COST = 1
TRAIN_MIN_HAPPY = 40           # a mopey pet won't learn
TRAIN_MAX_TRICKS = 8
TRICK_HAPPY = 5
TRICK_COOLDOWN = 15 * 60
TREAT_COST = 2
TREAT_HAPPY = 25
TREAT_HUNGER = 10
WALK_HAPPY = 10
WALK_HUNGER = 8
WALK_COOLDOWN = 45 * 60
WALK_GIFT_CHANCE = 0.15
SLEEP_HOURS = 8
SLEEP_HUNGER_FACTOR = 0.5      # a sleeping pet burns half the calories
WAKE_HAPPY = 5

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

_ADORE_SCENES = [
    "{name} melts into a puddle of pure contentment. You did that.",
    "{name} leans in, eyes half-closed, and makes the noise. THE noise.",
    "{name} accepts the adoration as its birthright, then demands more.",
    "{name} does a slow blink. In its language that's a love letter.",
    "{name} flops over, belly up, all defenses down. Trust: absolute.",
]
_ADORE_EGG_SCENES = [
    "You cup the egg in both hands. It warms, and something inside settles closer to the shell.",
    "The egg hums faintly against your palm. It doesn't know what you are yet. It knows it likes you.",
]
_ADORE_SLEEP_SCENES = [
    "{name} sighs in its sleep and burrows deeper. Whatever it's dreaming got better.",
    "You stroke {name} once, gently. One ear twitches. The dream continues.",
]

_TRAIN_WIN = [
    "{name} nails <b>{trick}</b> on the third try and looks at you like you invented applause.",
    "After a long negotiation, {name} performs <b>{trick}</b>. Genius confirmed.",
    "{name} learns <b>{trick}</b> suspiciously fast. Has it been practicing in secret?",
]
_TRAIN_FAIL = [
    "{name} watches the demonstration, considers it, and eats the cookie instead. Lesson postponed.",
    "{name} gets halfway through <b>{trick}</b> and gets distracted by its own tail. Tomorrow.",
    "{name} does something that is technically not <b>{trick}</b> but is, in fairness, adorable.",
]
_TRICK_SCENES = [
    "{name} performs <b>{trick}</b> for an audience of one. Standing ovation.",
    "On cue, {name} does <b>{trick}</b> — flawlessly, and then once more for the encore nobody asked for.",
    "{name} executes <b>{trick}</b> with the gravity of an Olympic final.",
]

_TREAT_SCENES = [
    "{name} receives the treat like a sacrament, then vibrates gently for several minutes.",
    "{name} inhales the treat, then checks your other hand. Then your pockets. Then your soul.",
    "{name} eats the treat in one go and immediately achieves enlightenment.",
]

_WALK_SCENES = [
    "{name} inspects every leaf on the route with forensic care. The walk takes forever. Worth it.",
    "{name} meets a dog, a pigeon and a leaf, and is equally thrilled by all three.",
    "{name} leads the whole way, tail up, as if it owns the street. Legally it might.",
    "{name} stops to stare at nothing for a full minute. You stare too. It's nice out.",
]
_WALK_SOUVENIRS = [
    "{name} brings home a stick that is clearly too big. It will be kept.",
    "{name} returns with one (1) pebble and presents it like a diamond.",
    "{name} comes back smelling of somewhere it shouldn't have been.",
]

_SLEEP_SCENES = [
    "You tuck {name} in. It resists for exactly four seconds, then is gone to the world.",
    "{name} circles three times, collapses, and starts a snore far too big for its body.",
]
_WAKE_SCENES = [
    "{name} wakes up, stretches to twice its length, and greets the day with a squeak.",
    "{name} surfaces from the nap refreshed, smug and ready for whatever this is.",
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


def _sleep_overlap_hours(state: dict, start: float, end: float) -> float:
    """Hours of [start, end] during which the pet was asleep."""
    s0, s1 = state.get("sleep_start"), state.get("asleep_until")
    if s0 is None or s1 is None:
        return 0.0
    return max(0.0, min(end, s1) - max(start, s0)) / 3600


def is_asleep(state: dict, now: float) -> bool:
    until = state.get("asleep_until")
    return until is not None and now < until


def sleep_wait(state: dict, now: float) -> float:
    until = state.get("asleep_until")
    return max(0.0, until - now) if until is not None else 0.0


def tick(state: dict, now: float) -> dict:
    """Fast-forward decay from last_tick to now (fractional hours exact).
    Sleeping hours burn half the hunger and cost no happiness."""
    start = state["last_tick"]
    hours = max(0.0, now - start) / 3600
    asleep = _sleep_overlap_hours(state, start, now)
    awake = max(0.0, hours - asleep)
    raw = state["hunger"] + HUNGER_PER_HOUR * (awake + asleep * SLEEP_HUNGER_FACTOR)
    state["hunger"] = min(100.0, raw)
    state["happiness"] = max(0.0, state["happiness"] - HAPPY_PER_HOUR * awake)
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
    return max(0.0, last + PLAY_COOLDOWN - now) if last is not None else 0.0


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


def adore(state: dict, user_id: int, user_name: str, now: float) -> str:
    """Affection: free, but each person's cuddles only land every ADORE_COOLDOWN."""
    fans = state.setdefault("adored_by", {})
    fan = fans.setdefault(str(user_id), {"name": user_name, "count": 0, "last": None})
    fan["name"] = user_name
    if fan["last"] is not None and now - fan["last"] < ADORE_COOLDOWN:
        return "cooldown"
    fan["last"] = now
    fan["count"] += 1
    state["happiness"] = min(100.0, state["happiness"] + ADORE_HAPPY)
    return "ok"


def train_chance(happiness: float) -> float:
    """A happy pet learns; a mopey one refuses. 40% at the floor, 90% when elated."""
    span = max(1.0, 100.0 - TRAIN_MIN_HAPPY)
    return 0.4 + 0.5 * min(1.0, max(0.0, happiness - TRAIN_MIN_HAPPY) / span)


def train(state: dict, trick: str, now: float, rng=random) -> str:
    """'mopey' | 'known' | 'full' | 'learned' | 'failed'. Cookie is charged
    on learned and failed alike — tuition is tuition."""
    if state["happiness"] < TRAIN_MIN_HAPPY:
        return "mopey"
    tricks = state.setdefault("tricks", [])
    if trick.lower() in (t.lower() for t in tricks):
        return "known"
    if len(tricks) >= TRAIN_MAX_TRICKS:
        return "full"
    if rng.random() < train_chance(state["happiness"]):
        tricks.append(trick)
        state["happiness"] = min(100.0, state["happiness"] + TRICK_HAPPY)
        return "learned"
    state["hunger"] = max(0.0, state["hunger"] - 5)   # it ate the cookie anyway
    return "failed"


def trick_wait(state: dict, now: float) -> float:
    last = state.get("last_trick")
    return max(0.0, last + TRICK_COOLDOWN - now) if last is not None else 0.0


def perform_trick(state: dict, now: float, rng=random) -> str | None:
    """Returns the trick performed, or None on cooldown / no tricks known."""
    tricks = state.get("tricks") or []
    if not tricks or trick_wait(state, now) > 0:
        return None
    state["last_trick"] = now
    state["happiness"] = min(100.0, state["happiness"] + TRICK_HAPPY)
    return rng.choice(tricks)


def treat(state: dict, today: str) -> str:
    """One treat per chat per day; 'today' is the creator-local date string."""
    if state.get("treat_day") == today:
        return "had_one"
    state["treat_day"] = today
    state["happiness"] = min(100.0, state["happiness"] + TREAT_HAPPY)
    state["hunger"] = max(0.0, state["hunger"] - TREAT_HUNGER)
    return "ok"


def walk_wait(state: dict, now: float) -> float:
    last = state.get("last_walk")
    return max(0.0, last + WALK_COOLDOWN - now) if last is not None else 0.0


def walk(state: dict, now: float) -> str:
    if walk_wait(state, now) > 0:
        return "cooldown"
    state["happiness"] = min(100.0, state["happiness"] + WALK_HAPPY)
    state["hunger"] = min(100.0, state["hunger"] + WALK_HUNGER)
    state["last_walk"] = now
    _update_starvation(state, now)
    return "ok"


def put_to_sleep(state: dict, now: float) -> str:
    if is_asleep(state, now):
        return "asleep"
    state["sleep_start"] = now
    state["asleep_until"] = now + SLEEP_HOURS * 3600
    state["woke_announced"] = False
    return "ok"


def maybe_wake(state: dict, now: float) -> bool:
    """True once, the first time the pet is seen after a nap ended."""
    until = state.get("asleep_until")
    if until is None or now < until or state.get("woke_announced", True):
        return False
    state["woke_announced"] = True
    state["happiness"] = min(100.0, state["happiness"] + WAKE_HAPPY)
    return True


def parents_board(state: dict) -> list[tuple[str, int, int]]:
    """[(name, feedings, adorations)] sorted by feedings then adorations."""
    rows: dict[str, list] = {}
    for uid, p in state.get("fed_by", {}).items():
        rows.setdefault(uid, [p["name"], 0, 0])[1] = p["count"]
    for uid, p in state.get("adored_by", {}).items():
        r = rows.setdefault(uid, [p["name"], 0, 0])
        r[0] = p["name"]
        r[2] = p["count"]
    return sorted(((n, f, a) for n, f, a in rows.values()), key=lambda r: (-r[1], -r[2], r[0]))


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
        f"<code>Hunger:    {bar(100 - state['hunger'])}</code> {hunger_mood(state['hunger'])}",
        f"<code>Happiness: {bar(state['happiness'])}</code> {happiness_mood(state['happiness'])}",
    ]
    if state["fed_by"]:
        top = max(state["fed_by"].values(), key=lambda p: p["count"])
        lines.append(
            f"Top parent: {html.escape(top['name'])} "
            f"({top['count']} feeding{'s' if top['count'] != 1 else ''})"
        )
    fans = state.get("adored_by") or {}
    if fans:
        fav = max(fans.values(), key=lambda p: p["count"])
        lines.append(f"Favorite human: {html.escape(fav['name'])} ({fav['count']} 🫶)")
    tricks = state.get("tricks") or []
    if tricks:
        lines.append("Tricks: " + ", ".join(html.escape(t) for t in tricks))
    if is_asleep(state, now):
        mins = int(sleep_wait(state, now) // 60) + 1
        lines.append(f"💤 asleep — wakes in ~{mins} min")
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

    if maybe_wake(state, now):
        db.save_pet(chat_id, state)
        await msg.reply_html("🌅 " + random.choice(_WAKE_SCENES).format(name=safe))

    if is_asleep(state, now) and sub in ("feed", "play", "train", "trick", "treat", "walk"):
        mins = int(sleep_wait(state, now) // 60) + 1
        await msg.reply_html(f"💤 {safe} is fast asleep — wakes in ~{mins} min. Let it dream.")
        return

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
    elif sub in ("adore", "cuddle", "pet", "love"):
        result = adore(state, user.id, user.first_name, now)
        db.save_pet(chat_id, state)
        if result == "cooldown":
            await msg.reply_html(
                f"{safe} accepts the affection but is, frankly, saturated. "
                f"Come back in a bit; scarcity is romance."
            )
            return
        label, _ = stage_of(state, now)
        if label == "egg":
            await msg.reply_html("🥚 " + random.choice(_ADORE_EGG_SCENES))
        elif is_asleep(state, now):
            await msg.reply_html("💤 " + random.choice(_ADORE_SLEEP_SCENES).format(name=safe))
        else:
            await msg.reply_html("🫶 " + random.choice(_ADORE_SCENES).format(name=safe))
    elif sub == "train":
        trick = " ".join(args[1:]).strip()
        label, _ = stage_of(state, now)
        if label == "egg":
            await msg.reply_html("🥚 You can't train an egg. You can only believe in it.")
            return
        if not trick or len(trick) > 30:
            await msg.reply_text(f"/pet train <trick> (30 characters max) — costs {TRAIN_COST} 🍪, tuition non-refundable.")
            return
        if db.get_cookies(chat_id, user.id) < TRAIN_COST:
            await msg.reply_text(f"Training costs {TRAIN_COST} 🍪 and you're broke. {name} respects the hustle anyway.")
            return
        result = train(state, trick, now)
        if result == "mopey":
            await msg.reply_html(f"{safe} is too mopey to learn anything right now. Play first, teach later.")
            return
        if result == "known":
            await msg.reply_html(f"{safe} already knows <b>{html.escape(trick)}</b> and is offended you forgot.")
            return
        if result == "full":
            await msg.reply_html(f"{safe} knows {TRAIN_MAX_TRICKS} tricks and its tiny brain is full. A legend, retired.")
            return
        db.add_cookies(chat_id, user.id, -TRAIN_COST, "pet training")
        db.save_pet(chat_id, state)
        bank = _TRAIN_WIN if result == "learned" else _TRAIN_FAIL
        icon = "🎓" if result == "learned" else "📚"
        await msg.reply_html(f"{icon} " + random.choice(bank).format(name=safe, trick=html.escape(trick)))
    elif sub in ("trick", "tricks"):
        tricks = state.get("tricks") or []
        if not tricks:
            await msg.reply_html(f"{safe} knows no tricks yet. /pet train <trick> ({TRAIN_COST} 🍪).")
            return
        if sub == "tricks":
            await msg.reply_html(f"{safe} knows: " + ", ".join(f"<b>{html.escape(t)}</b>" for t in tricks))
            return
        performed = perform_trick(state, now)
        db.save_pet(chat_id, state)
        if performed is None:
            mins = int(trick_wait(state, now) // 60) + 1
            await msg.reply_html(f"{safe} is not a performing monkey. (Well. Try again in ~{mins} min.)")
            return
        await msg.reply_html("🎪 " + random.choice(_TRICK_SCENES).format(name=safe, trick=html.escape(performed)))
        await _maybe_gift(msg, user, chat_id, name)
    elif sub == "treat":
        today = datetime.now(LOCAL_TZ).date().isoformat()
        if state.get("treat_day") == today:
            await msg.reply_html(f"{safe} already had today's treat and is pretending otherwise. Nice try. Tomorrow.")
            return
        if db.get_cookies(chat_id, user.id) < TREAT_COST:
            await msg.reply_text(f"A treat costs {TREAT_COST} 🍪. {name} watches your empty hands with enormous forgiveness.")
            return
        treat(state, today)
        db.add_cookies(chat_id, user.id, -TREAT_COST, "pet treat")
        db.save_pet(chat_id, state)
        await msg.reply_html("🍬 " + random.choice(_TREAT_SCENES).format(name=safe))
    elif sub == "walk":
        label, _ = stage_of(state, now)
        if label == "egg":
            await msg.reply_html("🥚 You carry the egg around the block. Neighbours have questions. The egg has none.")
            return
        result = walk(state, now)
        db.save_pet(chat_id, state)
        if result == "cooldown":
            mins = int(walk_wait(state, now) // 60) + 1
            await msg.reply_html(f"{safe} just got back and is lying in a sunbeam. Try again in ~{mins} min.")
            return
        text = "🦮 " + random.choice(_WALK_SCENES).format(name=safe)
        if random.random() < WALK_GIFT_CHANCE:
            db.add_cookies(chat_id, user.id, 2, "pet walk find")
            text += f"\n✨ {safe} finds something on the way home and insists you have it: +2 🍪"
        elif random.random() < 0.3:
            text += "\n" + random.choice(_WALK_SOUVENIRS).format(name=safe)
        await msg.reply_html(text)
    elif sub in ("sleep", "nap", "bed"):
        result = put_to_sleep(state, now)
        db.save_pet(chat_id, state)
        if result == "asleep":
            mins = int(sleep_wait(state, now) // 60) + 1
            await msg.reply_html(f"{safe} is already asleep. ~{mins} min to go. Shh.")
            return
        await msg.reply_html(
            "💤 " + random.choice(_SLEEP_SCENES).format(name=safe)
            + f"\n(Asleep for {SLEEP_HOURS}h: half the appetite, no moping, no playing.)"
        )
    elif sub == "parents":
        board = parents_board(state)
        if not board:
            await msg.reply_html(f"Nobody has fed or adored {safe} yet. Historic neglect.")
            return
        medals = ["🥇", "🥈", "🥉"]
        lines = [f"👨‍👩‍👧 <b>{safe}'s people</b>"]
        for i, (n, f, a) in enumerate(board[:10]):
            lines.append(f"{medals[i] if i < 3 else '•'} {html.escape(n)} — {f} feeding{'s' if f != 1 else ''}, {a} 🫶")
        await msg.reply_html("\n".join(lines))
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
            "/pet — status · /pet adopt <name> · /pet feed (1 🍪) · /pet play · "
            "/pet adore · /pet walk · /pet treat (2 🍪, daily) · /pet train <trick> (1 🍪) · "
            "/pet trick · /pet sleep · /pet talk <message> · /pet parents · /pet rename <name>"
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
