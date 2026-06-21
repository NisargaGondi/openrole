#!/usr/bin/env bash
# Keep one CareerShift Chromium window open for fast people search (local Unix socket).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
exec "$ROOT/.venv/bin/python" -m openrole.scrapers.careershift_daemon run
