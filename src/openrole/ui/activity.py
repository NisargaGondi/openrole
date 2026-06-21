"""Unified activity log for scout, ingest, and pipeline operations."""

from __future__ import annotations

from datetime import datetime

import streamlit as st

LOG_KEY = "or_activity_log"


def log_activity(message: str, *, level: str = "info") -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    prefix = {"info": "·", "ok": "✓", "warn": "!", "err": "✗"}.get(level, "·")
    line = f"[{ts}] {prefix} {message}"
    _append_line(line)


def append_log_line(line: str) -> None:
    """Append a pre-formatted line (e.g. from pipeline stamp())."""
    _append_line(line)


def _append_line(line: str) -> None:
    logs: list[str] = st.session_state.setdefault(LOG_KEY, [])
    logs.append(line)
    if len(logs) > 200:
        st.session_state[LOG_KEY] = logs[-200:]


def get_activity_log() -> list[str]:
    return list(st.session_state.get(LOG_KEY) or [])


def clear_activity_log() -> None:
    st.session_state[LOG_KEY] = []
