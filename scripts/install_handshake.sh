#!/usr/bin/env bash
# Handshake MCP setup: browser binary + optional login.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-python3}"
if [[ -x "$ROOT/.venv/bin/python" ]]; then
  PYTHON="$ROOT/.venv/bin/python"
  PIP="$ROOT/.venv/bin/pip"
else
  PIP="$PYTHON -m pip"
fi

echo "Installing OpenRole with Handshake extra..."
"$PIP" install -e ".[handshake]"

echo "Downloading Patchright Chromium (~170MB, one-time)..."
# Cursor sandbox sets PLAYWRIGHT_BROWSERS_PATH — unset so browser lands in ~/Library/Caches/ms-playwright
env -u PLAYWRIGHT_BROWSERS_PATH "$PYTHON" -m patchright install chromium

echo ""
echo "Chromium ready. Log in to Handshake (opens a browser window):"
echo "  $PYTHON scripts/handshake_login.py --clear-profile --force"
echo ""
echo "Use --clear-profile if a previous login closed Chrome instantly (false positive)."
