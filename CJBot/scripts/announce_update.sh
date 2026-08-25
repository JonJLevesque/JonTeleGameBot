#!/bin/bash
# Post a changelog message to a chat as the bot. Used after deploying updates.
# Usage: TELEGRAM_BOT_TOKEN=... bash scripts/announce_update.sh <chat_id> "line 1" ["line 2" ...]
set -euo pipefail
: "${TELEGRAM_BOT_TOKEN:?TELEGRAM_BOT_TOKEN must be set}"
CHAT_ID="$1"; shift
TEXT="🛠 <b>Bot updated!</b>"
for line in "$@"; do
  TEXT="$TEXT
• $line"
done
curl -sf "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/sendMessage" \
  --data-urlencode "chat_id=$CHAT_ID" \
  --data-urlencode "text=$TEXT" \
  --data-urlencode "parse_mode=HTML" > /dev/null
echo "announced to $CHAT_ID"
