#!/bin/zsh
set -eu

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON_PATH="$PROJECT_ROOT/.venv/bin/python"
PLIST_PATH="$HOME/Library/LaunchAgents/com.local.financial-dashboard.sync.plist"

if [[ ! -x "$PYTHON_PATH" ]]; then
  echo "Create .venv and install dependencies before installing the scheduler."
  exit 1
fi

mkdir -p "$HOME/Library/LaunchAgents" "$PROJECT_ROOT/data"
sed \
  -e "s|__PROJECT_ROOT__|$PROJECT_ROOT|g" \
  -e "s|__PYTHON_PATH__|$PYTHON_PATH|g" \
  "$PROJECT_ROOT/scripts/com.local.financial-dashboard.sync.plist.template" > "$PLIST_PATH"

launchctl bootout "gui/$(id -u)" "$PLIST_PATH" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST_PATH"
echo "Installed daily update schedule at 8:15 PM local time."

