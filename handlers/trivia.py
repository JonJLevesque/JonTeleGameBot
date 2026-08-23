"""/trivia — pub-quiz rounds as native Telegram quiz polls. 🧠

One question per round: the bot posts a quiz poll (Telegram itself reveals
the right answer and who picked what), every correct answer earns cookies
while the poll is open, and the fastest correct answer earns a bonus.
Questions come fresh from the AI — optionally on a requested topic
(/trivia space) — with a static bank as the keyless fallback. Round state
is in-memory on purpose: a restart mid-poll forfeits that round's payout,
which is survivable.
"""
import html
import random
from collections import defaultdict, deque

from telegram import Update
from telegram.error import TelegramError
from telegram.ext import CommandHandler, ContextTypes, PollAnswerHandler

import ai
import db
import prompts
from .common import require_group

OPEN_SECONDS = 45
REWARD = 2       # 🍪 per correct answer
FIRST_BONUS = 1  # extra 🍪 for the fastest correct answer

_active: dict[str, dict] = {}    # poll_id -> round state
_chat_poll: dict[int, str] = {}  # chat_id -> its active poll_id
_recent_static: dict[int, deque] = defaultdict(lambda: deque(maxlen=15))


# ---------------------------------------------------------- pure round logic

def parse_quiz(text: str | None):
    """Parse the AI's five-line format: question, then four options with the
    single correct one prefixed '*'. Returns (question, options, correct
    index) or None — any malformed output falls back to the static bank.
    Length limits are Telegram's poll API caps, minus safety margin."""
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    if len(lines) != 5:
        return None
    question, options, correct = lines[0], [], None
    if not question or len(question) > 300:
        return None
    for i, raw in enumerate(lines[1:]):
        if raw.startswith("*"):
            if correct is not None:
                return None
            correct = i
            raw = raw.lstrip("*").strip()
        if not raw or len(raw) > 100:
            return None
        options.append(raw)
    if correct is None:
        return None
    return question, options, correct


def shuffle_quiz(options: list[str], correct: int, rng=random):
    """Shuffle answer positions (models and banks both favor a slot)."""
    order = list(range(len(options)))
    rng.shuffle(order)
    return [options[i] for i in order], order.index(correct)


def pick_static(chat_id: int, rng=random):
    """A bank question this chat hasn't seen recently."""
    seen = _recent_static[chat_id]
    pool = [q for q in prompts.TRIVIA if q[0] not in seen] or list(prompts.TRIVIA)
    question, right, wrong = rng.choice(pool)
    seen.append(question)
    return question, [right] + list(wrong), 0


def payout(winners_so_far: int) -> int:
    return REWARD + (FIRST_BONUS if winners_so_far == 0 else 0)


# ------------------------------------------------------------------ handlers

async def trivia_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_group(update):
        return
    msg = update.effective_message
    chat_id = update.effective_chat.id
    if _chat_poll.get(chat_id) in _active:
        await msg.reply_text(
            "One question at a time — this round is still open."
        )
        return
    topic = " ".join(context.args or []).strip()
    parsed = None
    if ai.ENABLED:
        extra = (
            f"Requested topic for this question: {topic}. "
            f"If it's unusable, pick something adjacent."
        ) if topic else None
        raw = await ai.generate(
            "trivia", chat_id,
            user_name=update.effective_user.first_name, extra=extra,
        )
        parsed = parse_quiz(raw)
    if parsed is None:
        parsed = pick_static(chat_id)
    question, options, correct = parsed
    options, correct = shuffle_quiz(options, correct)
    try:
        poll_msg = await msg.reply_poll(
            question, options,
            type="quiz", correct_option_id=correct,
            is_anonymous=False, open_period=OPEN_SECONDS,
        )
    except TelegramError:
        await msg.reply_text("Couldn't post the question — try again in a bit.")
        return
    poll_id = poll_msg.poll.id
    _active[poll_id] = {
        "chat_id": chat_id,
        "correct": correct,
        "answer": options[correct],
        "winners": [],  # (first_name, cookies) in answer order
    }
    _chat_poll[chat_id] = poll_id
    # Announce results just after Telegram closes the poll itself.
    context.job_queue.run_once(
        _close_job, OPEN_SECONDS + 2, data=poll_id,
        name=f"trivia-close-{poll_id}",
    )


async def on_poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Quiz votes are final (Telegram forbids retracting them), so paying
    out per-answer as they arrive is safe."""
    ans = update.poll_answer
    state = _active.get(ans.poll_id)
    if state is None or ans.user is None or not ans.option_ids:
        return
    if ans.option_ids[0] == state["correct"]:
        cookies = payout(len(state["winners"]))
        db.add_cookies(state["chat_id"], ans.user.id, cookies, "trivia")
        state["winners"].append((ans.user.first_name, cookies))


async def _close_job(context: ContextTypes.DEFAULT_TYPE):
    state = _active.pop(context.job.data, None)
    if state is None:
        return
    chat_id = state["chat_id"]
    if _chat_poll.get(chat_id) == context.job.data:
        del _chat_poll[chat_id]
    answer = html.escape(state["answer"])
    if state["winners"]:
        parts = ", ".join(
            f"{html.escape(n)} +{c} 🍪" for n, c in state["winners"]
        )
        text = (
            f"🧠 Time! It was <b>{answer}</b>. {parts} — "
            f"fastest answer took the bonus. Another? /trivia"
        )
    else:
        text = (
            f"🧠 Time! It was <b>{answer}</b>, and nobody found it. "
            f"I'll pretend I didn't see that. /trivia to restore honor."
        )
    try:
        await context.bot.send_message(chat_id, text, parse_mode="HTML")
    except TelegramError:
        pass


def get_handlers():
    return [
        CommandHandler("trivia", trivia_cmd),
        PollAnswerHandler(on_poll_answer),
    ]
