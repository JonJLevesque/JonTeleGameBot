"""Configuration loaded from environment variables."""
import os

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
DB_PATH = os.environ.get("BOT_DB_PATH", "partybot.db")

# Optional: enables AI-generated prompts (fresh every time, never runs out).
# Without a key the bot falls back to the static banks in prompts.py.
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
AI_MODEL = os.environ.get("AI_MODEL", "claude-haiku-4-5")

if not BOT_TOKEN:
    raise SystemExit(
        "TELEGRAM_BOT_TOKEN is not set.\n"
        "Get a token from @BotFather and run:\n"
        "  export TELEGRAM_BOT_TOKEN='123456:ABC-your-token'"
    )
