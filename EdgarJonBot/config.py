"""Configuration from environment variables."""
import os

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
DB_PATH = os.environ.get("BOT_DB_PATH", "edgarjon.db")
ADMIN_ID = int(os.environ.get("BOT_ADMIN_ID", "0") or 0)
LOG_DIR = os.environ.get(
    "BOT_LOG_DIR", os.path.expanduser("~/Library/Logs/edgarjonbot")
)
BACKUP_DIR = os.environ.get("BOT_BACKUP_DIR", "backups")

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
AI_MODEL = os.environ.get("AI_MODEL", "claude-opus-5")

# GitHub connector: a token with repo read scope. Falls back to `gh auth token`.
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_POLL_SECONDS = int(os.environ.get("GITHUB_POLL_SECONDS", "180"))

# The bot's name as it introduces itself and how it's addressed in chat.
BOT_NAME = os.environ.get("BOT_NAME", "Edgar Jr.")
# Probability (0-1) that the bot butts into a conversation unprompted.
CHIME_IN_RATE = float(os.environ.get("BOT_CHIME_IN_RATE", "0.04"))
# Passive listening: run an extraction pass after this many new messages,
# or once the chat has gone quiet for IDLE_MINUTES with a few unread ones.
EXTRACT_EVERY = int(os.environ.get("BOT_EXTRACT_EVERY", "12"))
EXTRACT_IDLE_MINUTES = int(os.environ.get("BOT_EXTRACT_IDLE_MINUTES", "15"))

if not BOT_TOKEN:
    raise SystemExit(
        "TELEGRAM_BOT_TOKEN is not set.\n"
        "Create the bot with @BotFather, then:\n"
        "  export TELEGRAM_BOT_TOKEN='123456:ABC-your-token'\n"
        "Also run /setprivacy -> Disable in @BotFather so it can listen."
    )
