#!/usr/bin/env bash
# Stop OpenRole API (8000) and web (3000) dev servers.
set -euo pipefail

API_PORT="${OPENROLE_API_PORT:-8000}"
WEB_PORT="${OPENROLE_WEB_PORT:-3000}"

kill_port() {
  local port="$1"
  local pids
  pids=$(lsof -ti ":$port" 2>/dev/null || true)
  if [[ -n "${pids:-}" ]]; then
    echo "Stopping port $port: $pids"
    kill $pids 2>/dev/null || true
    sleep 0.5
    kill -9 $pids 2>/dev/null || true
  else
    echo "Nothing on port $port"
  fi
}

kill_port "$API_PORT"
kill_port "$WEB_PORT"

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [[ -f "$ROOT/scripts/careershift_daemon_ctl.sh" ]]; then
  bash "$ROOT/scripts/careershift_daemon_ctl.sh" stop 2>/dev/null || true
fi
if [[ -f "$ROOT/scripts/handshake_daemon_ctl.sh" ]]; then
  bash "$ROOT/scripts/handshake_daemon_ctl.sh" stop 2>/dev/null || true
fi

LOCK="$ROOT/web/.next/dev/lock"
if [[ -f "$LOCK" ]]; then
  rm -f "$LOCK"
  echo "Removed Next.js dev lock"
fi

echo "Done."
