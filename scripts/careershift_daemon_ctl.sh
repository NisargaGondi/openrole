#!/usr/bin/env bash
# Control CareerShift daemon: status | stop
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
ACTION="${1:-status}"
exec "$ROOT/.venv/bin/python" -m openrole.scrapers.careershift_daemon "$ACTION"
