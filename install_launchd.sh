#!/bin/zsh
set -euo pipefail

PROJECT_DIR="/Users/temirkanseudzen/assistant-telegram-bot"
AGENT_LABEL="com.temirkan.assistant-bot"
SOURCE_PLIST="$PROJECT_DIR/launchd/$AGENT_LABEL.plist"
TARGET_PLIST="$HOME/Library/LaunchAgents/$AGENT_LABEL.plist"

mkdir -p "$HOME/Library/LaunchAgents" "$PROJECT_DIR/logs"
chmod +x "$PROJECT_DIR/scripts/start_bot.sh"

launchctl unload "$TARGET_PLIST" 2>/dev/null || true
cp "$SOURCE_PLIST" "$TARGET_PLIST"
launchctl load "$TARGET_PLIST"
launchctl start "$AGENT_LABEL"

echo "LaunchAgent installed and started: $AGENT_LABEL"
