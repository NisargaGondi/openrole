"""Persist Job Scout run history for UI and cron."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from openrole.config import _REPO_ROOT

_LOG_PATH = _REPO_ROOT / "data" / "scout_run_log.json"
_MAX_ENTRIES = 50


def _ensure_parent() -> None:
    _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def load_scout_runs(*, limit: int = 10) -> list[dict[str, Any]]:
    if not _LOG_PATH.is_file():
        return []
    try:
        rows = json.loads(_LOG_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    if not isinstance(rows, list):
        return []
    return rows[:limit]


def last_scout_run() -> dict[str, Any] | None:
    rows = load_scout_runs(limit=1)
    return rows[0] if rows else None


def append_scout_run(report: dict[str, Any], *, trigger: str = "manual") -> dict[str, Any]:
    """Append a scout report to the log file (newest first)."""
    _ensure_parent()
    entry = dict(report)
    entry["logged_at"] = datetime.now(timezone.utc).isoformat()
    entry["trigger"] = trigger

    rows: list[dict[str, Any]] = []
    if _LOG_PATH.is_file():
        try:
            raw = json.loads(_LOG_PATH.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                rows = raw
        except (json.JSONDecodeError, OSError):
            rows = []

    rows.insert(0, entry)
    _LOG_PATH.write_text(json.dumps(rows[:_MAX_ENTRIES], indent=2), encoding="utf-8")
    return entry
