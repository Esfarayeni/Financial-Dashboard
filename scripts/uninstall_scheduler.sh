#!/bin/zsh
set -eu

PLIST_PATH="$HOME/Library/LaunchAgents/com.local.financial-dashboard.sync.plist"
launchctl bootout "gui/$(id -u)" "$PLIST_PATH" 2>/dev/null || true
if [[ -f "$PLIST_PATH" ]]; then
  mv "$PLIST_PATH" "$HOME/.Trash/com.local.financial-dashboard.sync.plist"
fi
echo "Removed the financial dashboard update schedule."

