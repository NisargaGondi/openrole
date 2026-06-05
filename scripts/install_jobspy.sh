#!/usr/bin/env bash
# Install JobSpy when `pip install -e .` fails (common if repo path contains an apostrophe).
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

echo "Installing numpy/pandas wheels..."
"$PIP" install --only-binary=:all: "numpy>=1.26" "pandas>=2.1"

echo "Installing JobSpy (no dependency resolver — avoids broken numpy build)..."
"$PIP" install --no-deps "python-jobspy==1.1.82"

echo "Installing JobSpy runtime deps..."
"$PIP" install requests beautifulsoup4 tls-client markdownify regex

echo "Verifying JobSpy..."
"$PYTHON" -c "from jobspy import scrape_jobs; print('JobSpy OK')"
