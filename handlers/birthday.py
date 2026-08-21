"""Hidden birthday machinery. 🎂

Deliberately absent from /help and the command list — the party finds you.
Birthdays live in the `birthdays` table (seeded by the operator, one row
per person, each with their own IANA timezone). A 15-minute watcher job:

  * At midnight in the CELEBRANT'S timezone on their day: a full-blast
    celebration in every chat they're in — banner, an AI tribute written
    from the memory file (static fallback), a cookie gift plus a dice-roll
    bonus, and the persona treats them as royalty all day (the operator's
    butler register is suspended on their own birthday).
  * Three days before: everyone ELSE in their chats gets a quiet DM
    heads-up so a human plan can happen too.

`celebrated_year` / `reminded_year` gate each firing to once per year, so
the watcher can run as often as it likes and a restart can never double-
celebrate.
"""
import asyncio
import html
import logging
import random
from datetime import datetime, timedelta

from telegram.error import TelegramError
from telegram.ext import ContextTypes

import ai
import db
from .common import LOCAL_TZ

log = logging.getLogger("partybot.birthday")

GIFT_COOKIES = 15
REMIND_DAYS_AHEAD = 3

FALLBACK_TRIBUTES = [
    "Happy birthday, {name}! I checked the ledger: you have been an "
    "absolute joy to run games for. The court rules that today, you are "
    "right about everything. 🥂 To {name}!",
    "It's {name}'s birthday! By decree of the pigeon: today the cookies "
    "flow, the dares are optional, and the Wordle is beatable. 🥂 To {name}!",
]


def _tz(name: str):
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(name)
    except Exception:
        return LOCAL_TZ


def _next_occurrence(b, now: datetime) -> datetime:
    """The next midnight-anchored birthday date for this row (today counts)."""
    bday = now.replace(month=b["month"], day=b["day"], hour=0, minute=0,
                       second=0, microsecond=0)
    if bday.date() < now.date():
        bday = bday.replace(year=now.year + 1)
    return bday


def check(b, now: datetime) -> str | None:
    """Pure gate: what this row is due for at `now` (in the row's tz).
    Returns "celebrate", "remind", or None. Year fields make each fire
    at most once per year."""
    if (now.month, now.day) == (b["month"], b["day"]):
        return "celebrate" if b["celebrated_year"] < now.year else None
    nxt = _next_occurrence(b, now)
    if (now.date() == (nxt - timedelta(days=REMIND_DAYS_AHEAD)).date()
            and b["reminded_year"] < nxt.year):
        return "remind"
    return None


def is_birthday_today(user_id: int) -> bool:
    b = db.get_birthday(user_id)
    if b is None:
        return False
    now = datetime.now(_tz(b["tz"]))
    return (now.month, now.day) == (b["month"], b["day"])


async def _celebrate(context: ContextTypes.DEFAULT_TYPE, b) -> None:
    name = b["name"]
    for chat_id in db.chats_for_user(b["user_id"]):
        try:
            await context.bot.send_message(
                chat_id,
                f"🎂🎉🎊 <b>IT IS OFFICIALLY {html.escape(name.upper())}'S "
                f"BIRTHDAY</b> 🎊🎉🎂\n"
                f"(midnight has struck in {html.escape(b['tz'])} — "
                f"I've been waiting all year for this)",
                parse_mode="HTML",
            )
            tribute = await ai.generate(
                "birthday", chat_id, user_name=name,
                extra=f"The birthday person is {name}.",
            ) or random.choice(FALLBACK_TRIBUTES).format(name=name)
            await context.bot.send_message(chat_id, f"🕊️ {tribute}")
            dice = await context.bot.send_dice(chat_id, emoji="🎲")
            await asyncio.sleep(4)
            bonus = dice.dice.value
            total = db.add_cookies(
                chat_id, b["user_id"], GIFT_COOKIES + bonus, "birthday gift"
            )
            await context.bot.send_message(
                chat_id,
                f"🎁 Birthday gift: {GIFT_COOKIES} 🍪 + {bonus} from the "
                f"birthday dice = <b>+{GIFT_COOKIES + bonus} 🍪</b> "
                f"(now {total}). Spend them irresponsibly, "
                f"{html.escape(name)}.",
                parse_mode="HTML",
            )
        except TelegramError:
            log.exception("birthday celebration failed in chat %s", chat_id)


async def _remind(context: ContextTypes.DEFAULT_TYPE, b) -> None:
    """Quiet DM to everyone else who shares a chat with the celebrant."""
    when = f"{['','January','February','March','April','May','June','July','August','September','October','November','December'][b['month']]} {b['day']}"
    told: set[int] = set()
    for chat_id in db.chats_for_user(b["user_id"]):
        for m in db.chat_members(chat_id):
            uid = m["user_id"]
            if uid == b["user_id"] or uid in told:
                continue
            told.add(uid)
            try:
                await context.bot.send_message(
                    uid,
                    f"🤫 Psst — {b['name']}'s birthday is in "
                    f"{REMIND_DAYS_AHEAD} days ({when}). You didn't hear "
                    f"it from me. I have plans of my own; you should too. "
                    f"(/memories in the group might have gift ideas.)",
                )
            except TelegramError:
                pass  # DM closed; the bot's own celebration still fires


async def _watch_job(context: ContextTypes.DEFAULT_TYPE):
    for b in db.birthdays_all():
        now = datetime.now(_tz(b["tz"]))
        due = check(b, now)
        if due == "celebrate":
            # Mark first: a send failure must never re-fire the party.
            db.mark_birthday(b["user_id"], "celebrated_year", now.year)
            await _celebrate(context, b)
        elif due == "remind":
            db.mark_birthday(
                b["user_id"], "reminded_year", _next_occurrence(b, now).year
            )
            await _remind(context, b)


def schedule(app) -> None:
    app.job_queue.run_repeating(
        _watch_job, interval=900, first=60, name="birthday-watch"
    )
