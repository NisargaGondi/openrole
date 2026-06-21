"""Cooperative pipeline cancellation (checked during long-running steps)."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

from openrole.api.pipeline_run_store import is_cancel_requested

_active_job: ContextVar[str | None] = ContextVar("pipeline_cancel_job", default=None)


class PipelineCancelled(Exception):
    """Raised when the user requested cancel for the active pipeline job."""


@contextmanager
def pipeline_cancel_context(job_id: str) -> Iterator[None]:
    token = _active_job.set(job_id)
    try:
        yield
    finally:
        _active_job.reset(token)


def check_cancelled() -> None:
    job_id = _active_job.get()
    if job_id and is_cancel_requested(job_id):
        raise PipelineCancelled(f"Pipeline cancelled ({job_id[:8]}…)")


def is_pipeline_cancelled() -> bool:
    job_id = _active_job.get()
    return bool(job_id and is_cancel_requested(job_id))
