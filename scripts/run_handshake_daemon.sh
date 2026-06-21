#!/usr/bin/env bash
# Keep one Handshake MCP session open for fast scout searches (local Unix socket).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
exec "$ROOT/.venv/bin/python" -m openrole.scrapers.handshake_daemon run
