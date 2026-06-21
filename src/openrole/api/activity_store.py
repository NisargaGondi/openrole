"""In-memory activity log for API (shared across requests in dev)."""

from __future__ import annotations

from datetime import datetime
from threading import Lock

_lock = Lock()
_lines: list[dict] = []


def log(message: str, *, level: str = "info", icon: str | None = None) -> dict:
    entry = {
        "id": len(_lines) + 1,
        "time": datetime.now().strftime("%H:%M:%S"),
        "ago": "just now",
        "message": message,
        "level": level,
        "icon": icon or _icon_for(level, message),
    }
    with _lock:
        _lines.append(entry)
        if len(_lines) > 300:
            del _lines[:100]
    return entry


def get_lines(limit: int = 60) -> list[dict]:
    with _lock:
        return list(_lines[-limit:])


def clear() -> None:
    with _lock:
        _lines.clear()


def _icon_for(level: str, message: str) -> str:
    m = message.lower()
    if "view" in m or "profile" in m:
        return "zap"
    if "deliver" in m or "message" in m or "draft" in m:
        return "send"
    if "connect" in m:
        return "users"
    if "research" in m or "insight" in m:
        return "star"
    if "scout" in m:
        return "radar"
    if level == "err":
        return "alert"
    if level == "ok":
        return "check"
    return "dot"
