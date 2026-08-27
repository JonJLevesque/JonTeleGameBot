"""/usquiz — how well do you actually know each other? 💞

The bot takes one thing it has learned about one of you and turns it into a
quiz for the other: a native quiz poll, correct answer earns a 🍪. Runs
itself once a day at 13:00 once the memory file has enough to work with.
"""
import logging
from datetime import time as dtime

from telegram import Update
from telegram.error import TelegramError
from telegram.ext import CommandHandler, ContextTypes, PollAnswerHandler

import ai
import db
from .common import LOCAL_TZ, require_group

log = logging.getLogger("ajbot.usquiz")
MIN_MEMORIES = 5
REWARD = 1
_open: dict[str, dict] = {}   # poll_id -> {chat_id, subject_id, correct, paid}


def parse_quiz(text: str) -> tuple[str, str, list[str], int] | None:
    """(subject_name, question, options, correct_idx) from the 6-line format."""
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    if len(lines) < 6 or not lines[0].upper().startswith("SUBJECT:"):
        return None
    subject = lines[0].split(":", 1)[1].strip()
    question = lines[1][:290]
    opts, correct = [], -1
    for ln in lines[2:6]:
        if ln.startswith("*"):
            correct = len(opts)
            ln = ln[1:].strip()
        opts.append(ln[:95])
    if correct < 0 or len(opts) != 4 or not subject or not question:
        return None
    return subject, question, opts, correct


async def run_quiz(context, chat_id: int) -> str | None:
    """Post one quiz; returns an error string for the caller or None on success."""
    if not ai.ENABLED:
        return "The quizmaster is off duty (AI disabled)."
    members = db.chat_members(chat_id)
    if len(members) < 2:
        return "I need two of you in here for this."
    mem = db.random_memory(chat_id)
    if mem is None:
        return "I don't know enough about you two yet. Talk more, or tell me things."
    names = [m["first_name"] for m in members]
    raw = await ai.us_quiz(chat_id, mem["text"], names)
    parsed = parse_quiz(raw or "")
    if not parsed:
        return "The quizmaster fumbled that one — try again."
    subject, question, opts, correct = parsed
    subject_row = next((m for m in members if m["first_name"].lower() == subject.lower()), None)
    try:
        poll_msg = await context.bot.send_poll(
            chat_id, f"💞 {question}", opts, type="quiz", correct_option_id=correct,
            is_anonymous=False, open_period=120,
            explanation=f"From the file: {mem['text'][:180]}",
        )
    except TelegramError as e:
        log.warning("usquiz poll failed: %s", e)
        return "Couldn't post the poll."
    _open[poll_msg.poll.id] = {"chat_id": chat_id, "subject_id": subject_row["user_id"] if subject_row else None,
                               "correct": correct, "paid": set()}
    return None


async def usquiz_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_group(update):
        return
    await context.bot.send_chat_action(update.effective_chat.id, "typing")
    err = await run_quiz(context, update.effective_chat.id)
    if err:
        await update.effective_message.reply_text(err)


async def on_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ans = update.poll_answer
    st = _open.get(ans.poll_id)
    if not st or not ans.option_ids:
        return
    uid = ans.user.id
    if uid == st["subject_id"]:
        try:
            await context.bot.send_message(st["chat_id"], f"{ans.user.first_name}, it's about you — you don't get to answer. 🙈")
        except TelegramError:
            pass
        return
    if ans.option_ids[0] == st["correct"] and uid not in st["paid"]:
        st["paid"].add(uid)
        total = db.add_cookies(st["chat_id"], uid, REWARD, "us quiz")
        try:
            await context.bot.send_message(st["chat_id"], f"💞 {ans.user.first_name} knows their person. +{REWARD} 🍪 (now {total}).")
        except TelegramError:
            pass


async def _daily(context: ContextTypes.DEFAULT_TYPE):
    for chat_id in db.chats_with_min_members(2):
        if len(db.memories_all(chat_id)) >= MIN_MEMORIES:
            await run_quiz(context, chat_id)


def schedule(app) -> None:
    app.job_queue.run_daily(_daily, dtime(13, 0, tzinfo=LOCAL_TZ), name="us-quiz")


def get_handlers():
    # Group 6: trivia's PollAnswerHandler sits in group 0 and would otherwise
    # be the only one to see poll answers.
    return [CommandHandler(["usquiz", "quizus"], usquiz_cmd), (PollAnswerHandler(on_answer), 6)]
