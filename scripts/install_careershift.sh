#!/usr/bin/env bash
# CareerShift setup: Patchright Chromium + optional login.
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

echo "Installing OpenRole with CareerShift extra..."
"$PIP" install -e ".[careershift]"

echo "Downloading Patchright Chromium (~170MB, one-time)..."
env -u PLAYWRIGHT_BROWSERS_PATH "$PYTHON" -m patchright install chromium

echo ""
echo "Chromium ready. Log in to CareerShift (opens a browser window):"
echo "  $PYTHON scripts/careershift_login.py --clear-profile --force"
echo ""
echo "CMU signup (if needed): https://www.careershift.com/user/signup?group=CMU"
