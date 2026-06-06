#!/usr/bin/env bash
# Run Streamlit with the project venv (avoids ModuleNotFoundError for openrole/jobspy).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -x "$ROOT/.venv/bin/python" ]]; then
  echo "Missing .venv — create it first: python3 -m venv .venv && pip install -e \".[dev]\""
  exit 1
fi

exec "$ROOT/.venv/bin/streamlit" run src/openrole/ui/app.py "$@"
