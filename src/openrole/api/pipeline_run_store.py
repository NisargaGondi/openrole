"""Track in-flight pipeline runs and cancel requests."""

from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock

_lock = Lock()
_runs: dict[str, dict] = {}
_cancel: set[str] = set()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def start_run(job_id: str, *, step: str, company: str | None = None) -> dict:
    entry = {
        "job_id": job_id,
        "step": step,
        "company": company,
        "started_at": _now_iso(),
        "status": "running",
    }
    with _lock:
        _cancel.discard(job_id)
        _runs[job_id] = entry
    return entry


def finish_run(job_id: str, *, status: str = "done") -> None:
    with _lock:
        _cancel.discard(job_id)
        if job_id in _runs:
            _runs[job_id]["status"] = status
            _runs[job_id]["finished_at"] = _now_iso()
            del _runs[job_id]


def request_cancel(job_id: str) -> bool:
    with _lock:
        if job_id not in _runs:
            return False
        _cancel.add(job_id)
        _runs[job_id]["status"] = "cancelling"
        return True


def is_cancelling(job_id: str) -> bool:
    with _lock:
        return job_id in _cancel


def is_cancel_requested(job_id: str) -> bool:
    with _lock:
        return job_id in _cancel


def get_active_runs() -> list[dict]:
    with _lock:
        return [
            dict(v)
            for v in _runs.values()
            if v.get("status") in ("running", "cancelling")
        ]


def is_running(job_id: str | None = None) -> bool:
    with _lock:
        if job_id:
            entry = _runs.get(job_id)
            return bool(entry and entry.get("status") in ("running", "cancelling"))
        return any(v.get("status") in ("running", "cancelling") for v in _runs.values())
