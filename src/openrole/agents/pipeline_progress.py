"""Timestamped pipeline progress lines for the UI log monitor."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

ProgressCallback = Callable[[str], None]


def stamp(message: str) -> str:
    ts = datetime.now().strftime("%H:%M:%S")
    return f"[{ts}] {message}"


def progress_entry(message: str) -> dict[str, list[str]]:
    """Return a state patch fragment for OpenRoleState.progress_log reducer."""
    return {"progress_log": [stamp(message)]}


def format_node_update(node_name: str, update: dict[str, Any]) -> str:
    stage = update.get("pipeline_stage") or node_name
    parts = [stamp(f"▸ {node_name} → {stage}")]
    if update.get("contact_count") is not None:
        parts.append(stamp(f"   saved {update['contact_count']} contact(s)"))
    if update.get("errors"):
        for err in update["errors"][:3]:
            parts.append(stamp(f"   ✗ {err}"))
    completed = update.get("stages_completed") or []
    if completed:
        parts.append(stamp(f"   done: {', '.join(completed)}"))
    return "\n".join(parts)


def merge_stream_logs(node_name: str, update: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    if node_name == "__meta__":
        return lines
    for raw in update.get("progress_log") or []:
        if raw not in lines:
            lines.append(raw)
    lines.extend(format_node_update(node_name, update).splitlines())
    return lines
