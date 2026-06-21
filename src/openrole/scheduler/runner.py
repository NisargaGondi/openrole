"""Scheduled job scout runs."""

from __future__ import annotations

from typing import Any

from openrole.agents.job_scout import run_job_scout


def run_scheduled_scout(**kwargs: Any) -> dict[str, Any]:
    """Entry point for cron / launchd — returns JSON-serializable report."""
    kwargs.setdefault("trigger", "scheduled")
    report = run_job_scout(**kwargs)
    return report.to_dict()
