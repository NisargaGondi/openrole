"""LangGraph checkpointer — required for interrupts and resumable runs."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from langgraph.checkpoint.memory import MemorySaver

from openrole.config import get_settings


@lru_cache(maxsize=1)
def get_checkpointer():
    """Return a process-wide checkpointer (MemorySaver; durable metadata on Job rows)."""
    settings = get_settings()
    if settings.is_sqlite:
        Path("data").mkdir(parents=True, exist_ok=True)
    return MemorySaver()


def make_thread_id(*, job_id: str, run_id: str) -> str:
    return f"{job_id}:{run_id}"


def run_config(*, thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}}
