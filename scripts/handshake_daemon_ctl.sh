#!/usr/bin/env bash
# Control Handshake daemon: status | stop
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
ACTION="${1:-status}"
exec "$ROOT/.venv/bin/python" -m openrole.scrapers.handshake_daemon "$ACTION"
