"""Map Job rows to external tracker formats."""

from __future__ import annotations

from typing import Any

from openrole.db.models import Job


def job_to_tracker_row(job: Job, *, company_name: str | None = None) -> dict[str, Any]:
    """Map a Job to a flat tracker dict. Pass company_name when the Job is detached from a session."""
    scout = (job.raw_payload or {}).get("scout") or {}
    if company_name is None:
        company_name = _company_name_from_job(job)
    return {
        "job_id": job.id,
        "title": job.title,
        "company": company_name,
        "url": job.source_url or job.apply_url or "",
        "platform": job.source_platform or "",
        "status": job.status.value if job.status else "discovered",
        "relevance_score": scout.get("relevance_score"),
        "scout_source": scout.get("source"),
        "search_term": scout.get("search_term"),
        "opt_status": scout.get("opt_status"),
        "run_id": scout.get("run_id"),
        "discovered_at": scout.get("discovered_at"),
    }


def _company_name_from_job(job: Job) -> str:
    """Resolve company name without triggering a lazy load on a detached instance."""
    from sqlalchemy import inspect as sa_inspect

    if "company" not in sa_inspect(job).unloaded:
        company = job.company
        return company.name if company else ""
    if job.company_id:
        from openrole.db.models import Company
        from openrole.db.session import session_scope

        with session_scope() as session:
            company = session.get(Company, job.company_id)
            return company.name if company else ""
    return ""
