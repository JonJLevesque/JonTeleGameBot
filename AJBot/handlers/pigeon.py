"""/tell — the postcard desk. 📮

DM the bot a message for someone in your group and it delivers it to their
DMs, word for word, without you having to say it to them directly. If their
DM with the bot isn't open yet, the whisper waits in their inbox and the
bot teases them in the group with a "you've got mail" button.

Deliveries can also be scheduled (/tell audrey in 2h …, at 9pm, tomorrow)
or sealed as a /capsule that unlocks months later — a minutely courier job
delivers whatever has come due.
"""
import html
import random
import re
from datetime import datetime, timedelta, timezone

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import TelegramError
from telegram.ext import CommandHandler, ContextTypes

import db
from .common import LOCAL_TZ

MAX_LEN = 3000  # leaves headroom under Telegram's 4096-char message limit

_TAGLINES = [
    "A little bird told me. I am the little bird.",
    "Delivered word for word, as sworn under postal oath.",
    "I flew all this way, the least you could do is read it.",
    "No take-backs — the postcard has already been stamped.",
    "Contents faithfully transcribed. Your agent reads nothing. (Your agent reads everything.)",
]

USAGE = (
    "📮 <b>Postcard desk</b>\n\n"
    "Tell me something here in private and I'll deliver it for you:\n"
    "  <code>/tell Jon you were right about the movie</code>\n"
    "  <code>/tell @username miss you, dummy</code>\n\n"
    "Schedule it for later:\n"
    "  <code>/tell Jon in 2h don't forget the oven</code>\n"
    "  <code>/tell Jon at 9pm sweet dreams</code>\n"
    "  <code>/tell Jon tomorrow 8am good luck today!!</code>\n\n"
    "Or seal a time capsule — months from now, out of nowhere:\n"
    "  <code>/capsule Jon 6mo remember this day?</code>\n"
    "  <code>/capsule Jon i hope we made it to Paris</code> "
    "(no duration = it arrives when they least expect it)\n\n"
    "I deliver word for word, and I can only reach people who've talked "
    "in a group we share."
)

_DUR_RE = re.compile(r"^(\d+)([mhd])$")
_TIME_RE = re.compile(r"^(\d{1,2})(?::(\d{2}))?(am|pm)?$", re.IGNORECASE)
_CAPSULE_RE = re.compile(r"^(\d+)(w|mo|y)$", re.IGNORECASE)


# ------------------------------------------------------------ time parsing

def _parse_timespec(token: str) -> tuple[int, int] | None:
    """'21:30', '9am', '9:30pm', '9' -> (hour, minute), or None."""
    m = _TIME_RE.match(token)
    if not m:
        return None
    hour, minute = int(m.group(1)), int(m.group(2) or 0)
    ampm = (m.group(3) or "").lower()
    if ampm:
        if not 1 <= hour <= 12:
            return None
        hour = hour % 12 + (12 if ampm == "pm" else 0)
    elif hour > 23:
        return None
    if minute > 59:
        return None
    return hour, minute


def _to_utc(target: datetime) -> str:
    return target.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def parse_schedule(args: list[str], now: datetime | None = None):
    """Consume an optional schedule prefix ('in 2h' / 'at 9pm' / 'tomorrow
    [8am]') from the argument list. Returns (deliver_at, rest): a UTC
    'YYYY-MM-DD HH:MM:SS' string (None = deliver now) and the remaining
    message tokens. A prefix that doesn't fully match a schedule form is
    left untouched — '/tell audrey in a way you were right' stays a
    message, because 'a' is not a duration."""
    now = now or datetime.now(LOCAL_TZ)
    if not args:
        return None, args
    head = args[0].lower()
    target, rest = None, args
    if head == "in" and len(args) >= 2:
        m = _DUR_RE.match(args[1].lower())
        if m:
            n, unit = int(m.group(1)), m.group(2)
            unit_name = {"m": "minutes", "h": "hours", "d": "days"}[unit]
            target = now + timedelta(**{unit_name: n})
            rest = args[2:]
    elif head == "at" and len(args) >= 2:
        hm = _parse_timespec(args[1])
        if hm:
            target = now.replace(hour=hm[0], minute=hm[1],
                                 second=0, microsecond=0)
            if target <= now:
                target += timedelta(days=1)
            rest = args[2:]
    elif head == "tomorrow":
        hm = _parse_timespec(args[1]) if len(args) >= 2 else None
        base = now + timedelta(days=1)
        if hm:
            target = base.replace(hour=hm[0], minute=hm[1],
                                  second=0, microsecond=0)
            rest = args[2:]
        else:
            target = base.replace(hour=9, minute=0, second=0, microsecond=0)
            rest = args[1:]
    if target is None:
        return None, args
    return _to_utc(target), rest


def parse_capsule_duration(token: str) -> timedelta | None:
    """'2w', '6mo', '1y' -> timedelta, or None."""
    m = _CAPSULE_RE.match(token.lower())
    if not m:
        return None
    n, unit = int(m.group(1)), m.group(2).lower()
    return timedelta(days=n * {"w": 7, "mo": 30, "y": 365}[unit])


def _fmt_local(deliver_at_utc: str) -> str:
    """A UTC db timestamp as a friendly local time: 'Thu Aug 21 at 09:00'."""
    dt = datetime.strptime(deliver_at_utc, "%Y-%m-%d %H:%M:%S").replace(
        tzinfo=timezone.utc).astimezone(LOCAL_TZ)
    return f"{dt.strftime('%a %b')} {dt.day} at {dt.strftime('%H:%M')}"


# --------------------------------------------------------------- delivery

def _delivery_text(w) -> str:
    sender = html.escape(w["sender_name"])
    body = html.escape(w["message"])
    if w["kind"] == "capsule":
        try:
            sealed_dt = datetime.strptime(
                w["created_at"], "%Y-%m-%d %H:%M:%S"
            ).replace(tzinfo=timezone.utc).astimezone(LOCAL_TZ)
            sealed = f" on {sealed_dt.strftime('%B')} {sealed_dt.day}, {sealed_dt.year}"
        except (TypeError, ValueError):
            sealed = " a while ago"
        return (
            f"📜 <b>A time capsule has arrived!</b> {sender} sealed this"
            f"{sealed}:\n\n"
            f"“{body}”\n\n"
            f"<i>Carried through time, unopened, by your agent. 📮</i>"
        )
    return (
        f"📮 <b>Special delivery!</b> {sender} asked me "
        f"to tell you something:\n\n"
        f"“{body}”\n\n"
        f"<i>{random.choice(_TAGLINES)}</i>"
    )


async def _try_deliver(context: ContextTypes.DEFAULT_TYPE, whisper) -> bool:
    """DM one whisper to its recipient. False if their DM is closed."""
    try:
        await context.bot.send_message(
            whisper["recipient_id"],
            _delivery_text(whisper),
            parse_mode="HTML",
        )
    except TelegramError:
        return False
    db.mark_whisper_delivered(whisper["id"])
    return True


async def flush_inbox(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> int:
    """Deliver any waiting whispers to a user who just opened a DM with the
    bot; each sender is told their message finally arrived. Returns how many
    were delivered. Called from /inbox, the deep link, and /start."""
    delivered = 0
    for w in db.pending_whispers(user_id):
        if not await _try_deliver(context, w):
            break  # DM still closed; the rest would fail too
        delivered += 1
        what = "time capsule" if w["kind"] == "capsule" else "message"
        try:
            await context.bot.send_message(
                w["sender_id"],
                f"📮 Delivered! {w['recipient_name']} just picked up "
                f"your {what}.",
            )
        except TelegramError:
            pass  # sender's DM closed; they'll live
    return delivered


async def _tease_in_group(context: ContextTypes.DEFAULT_TYPE, whisper) -> bool:
    """Announce in a shared group that mail is waiting, with a button that
    deep-links into the bot's DM to collect it."""
    btn = InlineKeyboardMarkup([[InlineKeyboardButton(
        "📬 Collect your message",
        url=f"https://t.me/{context.bot.username}?start=inbox",
    )]])
    recipient = html.escape(whisper["recipient_name"])
    sender = html.escape(whisper["sender_name"])
    if whisper["kind"] == "capsule":
        text = (
            f"📜 Psst, {recipient} — a time capsule {sender} sealed long "
            f"ago has just unlocked! Tap below and hit Start to open it."
        )
    else:
        text = (
            f"📨 Psst, {recipient} — {sender} left a private message "
            f"with me for you! Tap below and hit Start to collect it."
        )
    for chat_id in db.shared_chats(whisper["sender_id"], whisper["recipient_id"]):
        try:
            await context.bot.send_message(
                chat_id, text, parse_mode="HTML", reply_markup=btn
            )
            return True
        except TelegramError:
            continue
    return False


# ------------------------------------------------------------ courier job

async def _courier_job(context: ContextTypes.DEFAULT_TYPE):
    """Minutely: deliver scheduled whispers and capsules that have come due."""
    for w in db.due_whispers():
        if await _try_deliver(context, w):
            what = ("time capsule" if w["kind"] == "capsule"
                    else "scheduled message")
            try:
                await context.bot.send_message(
                    w["sender_id"],
                    f"📮 Delivered! Your {what} for "
                    f"{w['recipient_name']} just arrived.",
                )
            except TelegramError:
                pass
        elif not w["teased"]:
            # DM closed: announce once, then wait for their inbox flush.
            if await _tease_in_group(context, w):
                db.mark_whisper_teased(w["id"])


def schedule(app) -> None:
    app.job_queue.run_repeating(
        _courier_job, interval=60, first=15, name="postcard-courier"
    )


# ------------------------------------------------------------------ helpers

async def _redirect_to_dm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    btn = InlineKeyboardMarkup([[InlineKeyboardButton(
        "📮 Whisper in my DMs",
        url=f"https://t.me/{context.bot.username}?start=tell",
    )]])
    await update.effective_message.reply_text(
        "🤫 Whispers are private! Tell me in my DMs and I'll "
        "deliver it for you.",
        reply_markup=btn,
    )


def _is_self(sender, token: str) -> bool:
    return (token.lstrip("@").lower() == (sender.username or "").lower()
            or token.lower() == sender.first_name.lower())


async def _resolve_or_explain(msg, sender, token: str):
    """Resolve a recipient token, replying with the reason on failure.
    Returns (user_id, first_name) or None."""
    candidates = db.resolve_recipient(sender.id, token)
    if not candidates:
        await msg.reply_html(
            f"I don't know <b>{html.escape(token)}</b> from any group we "
            f"share — I only learn people when they talk. Try their "
            f"@username, or have them send a message in the group first."
        )
        return None
    if len(candidates) > 1:
        names = ", ".join(html.escape(n) for _, n in candidates)
        await msg.reply_html(
            f"I know more than one <b>{html.escape(token)}</b> ({names}) — "
            f"use their @username so I deliver to the right door."
        )
        return None
    return candidates[0]


# ----------------------------------------------------------------- commands

async def tell_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    sender = update.effective_user

    if update.effective_chat.type != "private":
        await _redirect_to_dm(update, context)
        return

    args = context.args or []
    if len(args) < 2:
        await msg.reply_html(USAGE)
        return

    token = args[0]
    deliver_at, rest = parse_schedule(args[1:])
    message = " ".join(rest)
    if not message:
        await msg.reply_text(
            "There's a time and a place, but nothing to say — "
            "add the message after the schedule."
        )
        return
    if len(message) > MAX_LEN:
        await msg.reply_text(
            f"That's a whole novel ({len(message)} characters) — my wings "
            f"can carry {MAX_LEN}. Trim it down a bit?"
        )
        return

    if _is_self(sender, token):
        if deliver_at is None:
            await msg.reply_text(
                "Delivering a message to yourself? Done: you said "
                f"“{message}”. That'll be no charge."
            )
            return
        # A scheduled note to your future self is a legitimate delivery.
        recipient_id, recipient_name = sender.id, sender.first_name
    else:
        found = await _resolve_or_explain(msg, sender, token)
        if found is None:
            return
        recipient_id, recipient_name = found

    wid = db.create_whisper(
        sender.id, sender.first_name, recipient_id, recipient_name, message,
        deliver_at=deliver_at,
    )
    safe_name = html.escape(recipient_name)

    if deliver_at is not None:
        await msg.reply_html(
            f"📮 Scheduled! I'll deliver it to <b>{safe_name}</b> on "
            f"{_fmt_local(deliver_at)}. Consider it in the outbound mail."
        )
        return

    whisper = {
        "id": wid, "sender_id": sender.id, "sender_name": sender.first_name,
        "recipient_id": recipient_id, "recipient_name": recipient_name,
        "message": message, "kind": "whisper", "created_at": None,
    }
    if await _try_deliver(context, whisper):
        await msg.reply_html(
            f"📮 Delivered to <b>{safe_name}</b>, word for word. "
            f"What happens next is between you two."
        )
    elif await _tease_in_group(context, whisper):
        db.mark_whisper_teased(wid)
        await msg.reply_html(
            f"<b>{safe_name}</b> hasn't opened a DM with me yet, so I "
            f"couldn't knock directly — but I've left them a note in the "
            f"group (message contents sealed 🔏). It delivers the moment "
            f"they tap it."
        )
    else:
        await msg.reply_html(
            f"<b>{safe_name}</b> hasn't opened a DM with me yet, so it's "
            f"waiting in their inbox — it delivers as soon as they message "
            f"me or hit /start."
        )


async def capsule_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    sender = update.effective_user

    if update.effective_chat.type != "private":
        await _redirect_to_dm(update, context)
        return

    args = context.args or []
    if len(args) < 2:
        await msg.reply_html(USAGE)
        return

    token = args[0]
    duration = parse_capsule_duration(args[1])
    rest = args[2:] if duration else args[1:]
    message = " ".join(rest)
    if not message:
        await msg.reply_html(USAGE)
        return
    if len(message) > MAX_LEN:
        await msg.reply_text(
            f"That's a whole novel ({len(message)} characters) — my wings "
            f"can carry {MAX_LEN}. Trim it down a bit?"
        )
        return

    if _is_self(sender, token):
        # "Dear future me" is exactly what capsules are for.
        recipient_id, recipient_name = sender.id, sender.first_name
    else:
        found = await _resolve_or_explain(msg, sender, token)
        if found is None:
            return
        recipient_id, recipient_name = found

    secret = duration is None
    if secret:
        duration = timedelta(days=random.randint(60, 300))
    deliver_at = (datetime.now(timezone.utc) + duration).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    db.create_whisper(
        sender.id, sender.first_name, recipient_id, recipient_name, message,
        deliver_at=deliver_at, kind="capsule",
    )
    safe_name = html.escape(recipient_name)
    if secret:
        await msg.reply_html(
            f"📜 Sealed! Your time capsule for <b>{safe_name}</b> will "
            f"arrive when they least expect it. Even I've stopped looking "
            f"at the date."
        )
    else:
        await msg.reply_html(
            f"📜 Sealed! Your time capsule for <b>{safe_name}</b> unlocks "
            f"on {_fmt_local(deliver_at)}."
        )


async def inbox_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        await update.effective_message.reply_text(
            "📬 Your inbox is private — DM me /inbox to check it."
        )
        return
    n = await flush_inbox(context, update.effective_user.id)
    if n == 0:
        await update.effective_message.reply_text(
            "📭 No mail today. Someone can send you some with /tell!"
        )


async def inbox_from_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Deep-link entry: the recipient tapped the group's Collect button."""
    n = await flush_inbox(context, update.effective_user.id)
    if n == 0:
        await update.effective_message.reply_text(
            "📭 Looks like that message was already delivered — "
            "check just above!"
        )


async def tell_from_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Deep-link entry: someone tapped 'Whisper in my DMs' in the group."""
    await update.effective_message.reply_html(USAGE)


def get_handlers():
    return [
        CommandHandler("tell", tell_cmd),
        CommandHandler("capsule", capsule_cmd),
        CommandHandler("inbox", inbox_cmd),
    ]
