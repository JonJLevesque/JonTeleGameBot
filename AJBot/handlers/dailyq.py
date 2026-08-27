"""Daily question ritual: /dailyq — one question a day, escalating intimacy.

Inspired by Aron's "36 questions": the bot posts one question per day on a
schedule, walking an ordered arc from light get-to-know-you through personal
to intimate (and, when /spicymode is on, steamy). The per-chat position in
the arc and the posting time live in SQLite; jobs are re-registered on every
bot start. Once the scripted arc runs out, questions are AI-generated at the
deepest stage (falling back to reprises of the deep half of the arc).

  /dailyq on [HH:MM]  — start the ritual (default 20:00)
  /dailyq now         — post today's question immediately
  /dailyq off         — stop it
"""
import html as _html
import logging
import random
import re
from datetime import time

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

import ai
import db
import prompts
from .common import LOCAL_TZ, require_group

log = logging.getLogger("ajbot.dailyq")

DEFAULT_TIME = (20, 0)  # 8pm local: intimate questions are evening questions

_STAGES = [
    (12, "Stage: warm-up — light, fun, zero risk."),
    (24, "Stage: personal — values, history, self-image."),
    (36, "Stage: closer — about the two of them specifically."),
    (48, "Stage: deep — vulnerability, the relationship, the future."),
]


def _sequence(spicy: bool) -> list[str]:
    seq = list(prompts.DAILY_QUESTIONS)
    if spicy:
        seq += prompts.DAILY_QUESTIONS_SPICY
    return seq


def _stage_note(idx: int) -> str:
    for limit, note in _STAGES:
        if idx < limit:
            return note
    return (
        "Stage: past the scripted arc — as deep and intimate as the earlier "
        "questions ever got, ideally braver. These two have been answering a "
        "daily question for months; nothing surface-level."
    )


async def _post_question(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    row = db.dailyq_get(chat_id)
    idx = row["idx"] if row else 0
    spicy = db.is_spicy(chat_id)
    seq = _sequence(spicy)
    question = None
    if idx < len(seq):
        question = seq[idx]
    else:
        question = await ai.generate(
            "dailyq", chat_id,
            duo=len(db.chat_members(chat_id)) == 2,
            spicy=spicy, user_name="both players",
            extra=_stage_note(idx),
        )
        if not question:  # no API key or generation failed: reprise the deep end
            question = random.choice(seq[len(seq) // 2:]) + "  (encore)"
    await context.bot.send_message(
        chat_id,
        f"💬 <b>Daily Question #{idx + 1}</b>\n\n{_html.escape(question)}\n\n"
        f"<i>Both of you answer. No skipping.</i>",
        parse_mode="HTML",
    )
    db.dailyq_bump(chat_id)  # advance only after a successful send


async def _job(context: ContextTypes.DEFAULT_TYPE):
    try:
        await _post_question(context, context.job.chat_id)
    except Exception:
        log.exception("daily question failed for chat %s", context.job.chat_id)


def _schedule(job_queue, chat_id: int, hour: int, minute: int) -> None:
    for job in job_queue.get_jobs_by_name(f"dailyq:{chat_id}"):
        job.schedule_removal()
    job_queue.run_daily(
        _job, time(hour, minute, tzinfo=LOCAL_TZ),
        chat_id=chat_id, name=f"dailyq:{chat_id}",
    )


def restore_jobs(app: Application) -> None:
    """Re-register every chat's daily job after a restart."""
    for row in db.dailyq_all():
        _schedule(app.job_queue, row["chat_id"], row["hour"], row["minute"])
        log.info("dailyq restored for chat %s at %02d:%02d",
                 row["chat_id"], row["hour"], row["minute"])


async def dailyq_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_group(update):
        return
    msg = update.effective_message
    chat_id = update.effective_chat.id
    arg = context.args[0].lower() if context.args else ""
    row = db.dailyq_get(chat_id)

    if arg == "off":
        db.dailyq_off(chat_id)
        for job in context.job_queue.get_jobs_by_name(f"dailyq:{chat_id}"):
            job.schedule_removal()
        await msg.reply_text("💬 Daily questions stopped. /dailyq on to resume the arc.")
        return

    if arg == "now":
        if row is None:
            db.dailyq_set(chat_id, *DEFAULT_TIME)
            _schedule(context.job_queue, chat_id, *DEFAULT_TIME)
        await _post_question(context, chat_id)
        return

    if arg == "on":
        hour, minute = DEFAULT_TIME
        if len(context.args) > 1:
            m = re.fullmatch(r"(\d{1,2}):(\d{2})", context.args[1])
            if not m or int(m[1]) > 23 or int(m[2]) > 59:
                await msg.reply_text("Time must be HH:MM (24h), e.g. /dailyq on 21:30")
                return
            hour, minute = int(m[1]), int(m[2])
        db.dailyq_set(chat_id, hour, minute)
        _schedule(context.job_queue, chat_id, hour, minute)
        await msg.reply_html(
            f"💬 <b>Daily Question</b> is on — every day at {hour:02d}:{minute:02d}.\n"
            f"One question a day, and they get deeper as the days go. "
            f"Both of you answer. (/dailyq now to get today's immediately.)"
        )
        return

    # status
    if row is None:
        await msg.reply_text(
            "💬 Daily questions are off. /dailyq on [HH:MM] starts the ritual — "
            "one question a day, escalating."
        )
    else:
        await msg.reply_html(
            f"💬 Daily questions: <b>on</b>, {row['hour']:02d}:{row['minute']:02d} "
            f"daily, {row['idx']} asked so far. /dailyq now | off"
        )


def get_handlers():
    return [CommandHandler("dailyq", dailyq_cmd)]
