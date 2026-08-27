#!/bin/bash
# Install PartyBot as a macOS launchd agent: starts at login, restarts on
# crash, logs to ~/Library/Logs/partybot/. Secrets come from the environment
# at install time and are written only into the plist in ~/Library (never
# into the repo).
#
# Usage:  TELEGRAM_BOT_TOKEN=... [ANTHROPIC_API_KEY=...] [BOT_ADMIN_ID=...] \
#         bash scripts/install_launchd.sh
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.jonl.partybot"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOGDIR="$HOME/Library/Logs/partybot"

: "${TELEGRAM_BOT_TOKEN:?TELEGRAM_BOT_TOKEN must be set}"
mkdir -p "$LOGDIR" "$HOME/Library/LaunchAgents"

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
 "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$REPO/.venv/bin/python</string>
    <string>bot.py</string>
  </array>
  <key>WorkingDirectory</key><string>$REPO</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>TELEGRAM_BOT_TOKEN</key><string>$TELEGRAM_BOT_TOKEN</string>
    <key>ANTHROPIC_API_KEY</key><string>${ANTHROPIC_API_KEY:-}</string>
    <key>BOT_ADMIN_ID</key><string>${BOT_ADMIN_ID:-0}</string>
  </dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>15</integer>
  <key>StandardOutPath</key><string>$LOGDIR/launchd.log</string>
  <key>StandardErrorPath</key><string>$LOGDIR/launchd.log</string>
</dict>
</plist>
EOF
chmod 600 "$PLIST"

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "installed + started: $LABEL"
echo "logs:    $LOGDIR/partybot.log"
echo "control: launchctl kickstart -k gui/$(id -u)/$LABEL   # restart"
echo "         launchctl bootout gui/$(id -u)/$LABEL        # stop"
