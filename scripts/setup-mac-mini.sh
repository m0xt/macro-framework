#!/usr/bin/env bash
# One-shot Mac mini bootstrap for the macro-framework Tuesday refresh.
#
# Run this from inside the repo on the Mac mini:
#   cd /path/to/macro-framework && git pull && bash scripts/setup-mac-mini.sh

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LA_DIR="$HOME/Library/LaunchAgents"

[[ -d "$REPO/.git" ]] || { echo "ERROR: $REPO is not a git repo"; exit 1; }
cd "$REPO"
echo "Using repo: $REPO"

echo "==> 1. Homebrew"
if ! command -v brew >/dev/null 2>&1; then
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
fi
if [[ -x /opt/homebrew/bin/brew ]]; then
  eval "$(/opt/homebrew/bin/brew shellenv)"
elif [[ -x /usr/local/bin/brew ]]; then
  eval "$(/usr/local/bin/brew shellenv)"
fi

echo "==> 2. Pull latest code"
git pull --ff-only

echo "==> 3. Python venv"
if [[ ! -x .venv/bin/python ]]; then
  python3 -m venv .venv
fi
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt

echo "==> 4. LaunchAgent (substituting __REPO__ + __HOME__)"
mkdir -p "$LA_DIR" .cache
name="com.milkroad.macro-refresh"
src="scripts/${name}.plist"
dst="$LA_DIR/${name}.plist"
sed -e "s|__REPO__|$REPO|g" -e "s|__HOME__|$HOME|g" "$src" > "$dst"
launchctl unload "$dst" 2>/dev/null || true
launchctl load "$dst"

echo "==> 5. Sanity checks"
command -v claude >/dev/null \
  || echo "  WARN: 'claude' CLI not on PATH — install + authenticate before next Tuesday"
git remote -v | grep -q push \
  || echo "  WARN: no push remote configured"
if [[ ! -f .env ]] || ! grep -q SUPABASE_URL .env 2>/dev/null; then
  echo "  WARN: .env missing or no SUPABASE_URL — supabase sync will fail"
  echo "         create .env with SUPABASE_URL + SUPABASE_SERVICE_KEY"
fi

echo
echo "Done. Schedule: every Tuesday 11:00 Prague time."
echo "Logs: $REPO/.cache/launchd-refresh.log"
echo
echo "To test the script manually without waiting for Tuesday:"
echo "  bash scripts/tuesday.sh"
