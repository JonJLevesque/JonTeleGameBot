"""Entry point: wires the persistence layer and handlers into a PTB app."""
import logging

from telegram import BotCommand, Update
from telegram.ext import Application, ContextTypes, TypeHandler

import config
import db
from handlers import all_handlers, dailyq, track_users
from handlers.help import COMMAND_LIST

logging.basicConfig(
    format="%(asctime)s %(name)s %(levelname)s: %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("partybot")


async def _track(update: Update, context: ContextTypes.DEFAULT_TYPE):
    track_users(update)


async def _post_init(app: Application):
    await app.bot.set_my_commands(
        [BotCommand(cmd, desc) for cmd, desc in COMMAND_LIST]
    )
    dailyq.restore_jobs(app)
    log.info("Bot started as @%s", app.bot.username)


async def _on_error(update, context: ContextTypes.DEFAULT_TYPE):
    log.exception("Error handling update %s", update, exc_info=context.error)


def main():
    db.init(config.DB_PATH)
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
