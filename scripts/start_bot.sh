#!/bin/zsh
set -euo pipefail

PROJECT_DIR="/Users/temirkanseudzen/assistant-telegram-bot"
LOG_DIR="$PROJECT_DIR/logs"

mkdir -p "$LOG_DIR"
cd "$PROJECT_DIR"
source ".venv/bin/activate"
exec python "bot.py" >> "$LOG_DIR/bot.log" 2>&1
