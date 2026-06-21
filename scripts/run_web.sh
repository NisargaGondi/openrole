#!/usr/bin/env bash
# Start Next.js dev server — frees stale port/lock from prior runs.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WEB="$ROOT/web"
PORT="${OPENROLE_WEB_PORT:-3000}"

cd "$WEB"
export NEXT_PUBLIC_API_URL="${NEXT_PUBLIC_API_URL:-http://127.0.0.1:8000}"

# Kill anything already listening on our port (orphaned next dev)
if command -v lsof >/dev/null 2>&1; then
  stale_pids=$(lsof -ti ":$PORT" 2>/dev/null || true)
  if [[ -n "${stale_pids:-}" ]]; then
    echo "Stopping stale process(es) on port $PORT: $stale_pids"
    kill $stale_pids 2>/dev/null || true
    sleep 0.5
    kill -9 $stale_pids 2>/dev/null || true
  fi
fi

# Next.js 16 dev lock — prevents "Another next dev server is already running"
LOCK="$WEB/.next/dev/lock"
if [[ -f "$LOCK" ]]; then
  echo "Removing stale Next.js dev lock"
  rm -f "$LOCK"
fi

echo "OpenRole web → http://localhost:$PORT (API: $NEXT_PUBLIC_API_URL)"
exec npm run dev -- --port "$PORT"
