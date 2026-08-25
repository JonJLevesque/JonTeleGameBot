"""EdgarJonBot entry point."""
import html
import logging
import os
import time as _time
import traceback
from datetime import time
from logging.handlers import RotatingFileHandler

from telegram import BotCommand, Update
from telegram.error import Conflict, NetworkError, RetryAfter, TelegramError
from telegram.ext import Application, ContextTypes

import config
import db
from handlers import all_handlers, listener, reminders, shipping
from handlers.common import LOCAL_TZ
from handlers.help import COMMAND_LIST

os.makedirs(config.LOG_DIR, exist_ok=True)
logging.basicConfig(
    format="%(asctime)s %(name)s %(levelname)s: %(message)s", level=logging.INFO,
    handlers=[logging.StreamHandler(),
              RotatingFileHandler(os.path.join(config.LOG_DIR, "edgarjon.log"),
                                  maxBytes=5_000_000, backupCount=5)],
)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("edgarjon")
_last_alert = 0.0


async def _backup(context):
    try:
        log.info("backup: %s", db.backup(config.BACKUP_DIR))
    except Exception:
        log.exception("backup failed")


async def _post_init(app: Application):
    await app.bot.set_my_commands([BotCommand(c, d) for c, d in COMMAND_LIST])
    reminders.restore(app)
    shipping.schedule(app)
    listener.schedule(app)
    app.job_queue.run_daily(_backup, time(3, 45, tzinfo=LOCAL_TZ), name="backup")
    log.info("%s online as @%s (ai=%s, model=%s)", config.BOT_NAME, app.bot.username,
             __import__("ai").ENABLED, config.AI_MODEL)


async def _on_error(update, context: ContextTypes.DEFAULT_TYPE):
    global _last_alert
    log.exception("error on %s", update, exc_info=context.error)
    if isinstance(context.error, (NetworkError, Conflict, RetryAfter)):
        return
    if not config.ADMIN_ID or _time.time() - _last_alert < 300:
        return
    _last_alert = _time.time()
    tb = "".join(traceback.format_exception(context.error))[-1500:]
    try:
        await context.bot.send_message(
            config.ADMIN_ID, f"🚨 <b>{config.BOT_NAME} error</b>\n<pre>{html.escape(tb)}</pre>",
            parse_mode="HTML",
        )
    except TelegramError:
        pass


def main():
    db.init(config.DB_PATH)
    app = Application.builder().token(config.BOT_TOKEN).post_init(_post_init).build()
    for h in all_handlers():
        app.add_handler(h)
    app.add_error_handler(_on_error)
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
