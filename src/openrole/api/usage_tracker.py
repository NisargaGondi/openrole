"""Persist API usage and cost estimates per pipeline run / job."""

from __future__ import annotations

from sqlalchemy import func, select

from openrole.api.usage_store import cost_for_service, detect_services_in_message
from openrole.db.models import Job, UsageEvent
from openrole.db.session import session_scope


def record_usage(
    *,
    service: str,
    calls: int = 1,
    job_id: str | None = None,
    company: str | None = None,
    pipeline_step: str | None = None,
    detail: str | None = None,
) -> None:
    rate = cost_for_service(service)
    cost = round(calls * rate, 6)
    with session_scope() as session:
        session.add(
            UsageEvent(
                job_id=job_id,
                company=company,
                pipeline_step=pipeline_step,
                service=service,
                calls=calls,
                est_cost_usd=cost,
                detail=(detail or "")[:2000] or None,
            )
        )


def record_from_log_line(
    message: str,
    *,
    job_id: str | None = None,
    company: str | None = None,
    pipeline_step: str | None = None,
) -> None:
    for service, calls in detect_services_in_message(message).items():
        record_usage(
            service=service,
            calls=calls,
            job_id=job_id,
            company=company,
            pipeline_step=pipeline_step,
            detail=message[:500],
        )


def usage_summary_persisted() -> dict:
    with session_scope() as session:
        rows = list(session.scalars(select(UsageEvent).order_by(UsageEvent.created_at.desc()).limit(500)))
        if not rows:
            return _empty_summary()

        totals: dict[str, dict] = {}
        by_job: dict[str, dict] = {}
        for row in rows:
            svc = row.service
            bucket = totals.setdefault(
                svc,
                {"key": svc, "calls": 0, "est_cost_usd": 0.0, "rate_usd": cost_for_service(svc)},
            )
            bucket["calls"] += row.calls
            bucket["est_cost_usd"] = round(bucket["est_cost_usd"] + row.est_cost_usd, 6)

            if row.job_id:
                jb = by_job.setdefault(
                    row.job_id,
                    {
                        "job_id": row.job_id,
                        "company": row.company,
                        "total_cost_usd": 0.0,
                        "total_calls": 0,
                        "steps": {},
                        "services": {},
                    },
                )
                jb["total_cost_usd"] = round(jb["total_cost_usd"] + row.est_cost_usd, 6)
                jb["total_calls"] += row.calls
                if row.company and not jb.get("company"):
                    jb["company"] = row.company
                step = row.pipeline_step or "other"
                jb["steps"][step] = round(jb["steps"].get(step, 0.0) + row.est_cost_usd, 6)
                jb["services"][svc] = jb["services"].get(svc, 0) + row.calls

        # Enrich job titles
        job_ids = list(by_job.keys())
        if job_ids:
            jobs = {
                j.id: j
                for j in session.scalars(select(Job).where(Job.id.in_(job_ids))).all()
            }
            for jid, jb in by_job.items():
                job = jobs.get(jid)
                if job:
                    jb["job_title"] = job.title

        services = sorted(totals.values(), key=lambda x: x["key"])
        total_cost = round(sum(s["est_cost_usd"] for s in services), 4)
        history = sorted(by_job.values(), key=lambda x: x["total_cost_usd"], reverse=True)

        return {
            "services": services,
            "total_est_cost_usd": total_cost,
            "event_count": len(rows),
            "by_job": history[:30],
            "recent": [
                {
                    "service": r.service,
                    "calls": r.calls,
                    "est_cost_usd": r.est_cost_usd,
                    "job_id": r.job_id,
                    "company": r.company,
                    "pipeline_step": r.pipeline_step,
                    "detail": r.detail,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in rows[:40]
            ],
        }


def _empty_summary() -> dict:
    from openrole.config import get_settings

    services = [
        {"key": k, "calls": 0, "est_cost_usd": 0.0, "rate_usd": cost_for_service(k)}
        for k in (
            "tavily",
            "apollo",
            "jobspy",
            "handshake",
            "careershift",
            "notion",
        )
    ]
    for _role, model_id in get_settings().llm_models_summary().items():
        if _role == "provider":
            continue
        key = f"llm/{model_id}"
        services.append(
            {"key": key, "calls": 0, "est_cost_usd": 0.0, "rate_usd": cost_for_service(key)}
        )
    return {
        "services": services,
        "total_est_cost_usd": 0.0,
        "event_count": 0,
        "by_job": [],
        "recent": [],
    }
