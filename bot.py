"""Entry point: wires the persistence layer and handlers into a PTB app."""
import html
import logging
import os
import time as _time
import traceback
from datetime import time
from logging.handlers import RotatingFileHandler

from telegram import BotCommand, Update
from telegram.error import Conflict, NetworkError, RetryAfter, TelegramError
from telegram.ext import Application, ContextTypes, TypeHandler

import config
import db
from handlers import (
    all_handlers, dailyq, levels, pet, pigeon, recap, track_users,
)
from handlers import wordle as wordle_handlers
from handlers.common import LOCAL_TZ
from handlers.help import COMMAND_LIST

os.makedirs(config.LOG_DIR, exist_ok=True)
logging.basicConfig(
    format="%(asctime)s %(name)s %(levelname)s: %(message)s",
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(),
        RotatingFileHandler(
            os.path.join(config.LOG_DIR, "partybot.log"),
            maxBytes=5_000_000, backupCount=5,
        ),
    ],
)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("partybot")

_last_alert = 0.0  # error-DM rate limit


async def _track(update: Update, context: ContextTypes.DEFAULT_TYPE):
    track_users(update)


async def _backup_job(context: ContextTypes.DEFAULT_TYPE):
    try:
        dest = db.backup(config.BACKUP_DIR)
        log.info("db backup written: %s", dest)
    except Exception:
        log.exception("db backup failed")


async def _post_init(app: Application):
    await app.bot.set_my_commands(
        [BotCommand(cmd, desc) for cmd, desc in COMMAND_LIST]
    )
    dailyq.restore_jobs(app)
    recap.schedule(app)
    wordle_handlers.schedule_nudge(app)
    pigeon.schedule(app)
    levels.schedule(app)
    pet.schedule(app)
    app.job_queue.run_daily(
        _backup_job, time(3, 30, tzinfo=LOCAL_TZ), name="db-backup"
    )
    age = db.latest_backup_age_hours(config.BACKUP_DIR)
    if age is None or age > 24:
        await _backup_job(None)
    log.info("Bot started as @%s", app.bot.username)


async def _on_error(update, context: ContextTypes.DEFAULT_TYPE):
    log.exception("Error handling update %s", update, exc_info=context.error)
    global _last_alert
    err = context.error
    # Transient polling noise (Telegram 502s, restart overlaps, flood waits)
    # is logged but never alerted.
    if isinstance(err, (NetworkError, Conflict, RetryAfter)):
        return
    if not config.ADMIN_ID or _time.time() - _last_alert < 300:
        return
    _last_alert = _time.time()
    tb = "".join(traceback.format_exception(err))[-1500:]
    try:
        await context.bot.send_message(
            config.ADMIN_ID,
            f"🚨 <b>PartyBot error</b>\n<pre>{html.escape(tb)}</pre>",
            parse_mode="HTML",
        )
    except TelegramError:
        pass


def main():
    db.init(config.DB_PATH)
    # NOTE: updates are processed sequentially (concurrent_updates is off).
    # Several handlers rely on this — wordle's duel settlement and geo's
    # in-memory rounds have no locks of their own. If you ever enable
    # concurrent_updates, add per-chat locks there first (beautiful,
    # tournament and boardgames already have them).
    app = Application.builder().token(config.BOT_TOKEN).post_init(_post_init).build()

    # Group -1 runs before command handlers: cache every user we can see so
    # @username resolution and the leaderboard have names to work with.
    app.add_handler(TypeHandler(Update, _track), group=-1)

    for entry in all_handlers():
        if isinstance(entry, tuple):
            handler, group = entry
            app.add_handler(handler, group=group)
        else:
            app.add_handler(entry)
    app.add_error_handler(_on_error)

    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
