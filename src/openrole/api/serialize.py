"""Serialize DB models for JSON API responses."""

from __future__ import annotations

from typing import Any

from openrole.db.models import Contact, Job, Outreach, JOB_STATUS_LABELS
from openrole.db.repository import best_resume_report


def visa_summary_for_job(job: Job) -> dict[str, Any]:
    raw = job.raw_payload or {}
    visa_meta: dict[str, Any] = raw.get("llm_enrich") or {}
    scout: dict[str, Any] = raw.get("scout") or {}

    visa_status = visa_meta.get("visa_status") or scout.get("opt_status")
    if visa_status not in (None, "eligible", "ineligible", "unknown"):
        visa_status = None

    return {
        "visa_status": visa_status,
        "accepts_opt": visa_meta.get("accepts_opt"),
        "accepts_cpt": visa_meta.get("accepts_cpt"),
        "stem_opt_eligible": visa_meta.get("stem_opt_eligible"),
        "will_sponsor": visa_meta.get("will_sponsor"),
        "work_auth_us_only": visa_meta.get("work_auth_us_only"),
        "visa_notes": visa_meta.get("visa_notes"),
        "visa_confidence": visa_meta.get("visa_confidence"),
    }


def job_to_dict(job: Job) -> dict[str, Any]:
    scout = (job.raw_payload or {}).get("scout") or {}
    resume_report = best_resume_report(job.raw_payload)
    analyses_raw = (job.raw_payload or {}).get("resume_analyses") or {}
    resume_analyses = analyses_raw if isinstance(analyses_raw, dict) else {}
    company = job.company
    score = scout.get("relevance_score")
    return {
        "id": job.id,
        "title": job.title,
        "company": company.name if company else None,
        "company_id": job.company_id,
        "company_domain": company.domain if company else None,
        "department": job.department,
        "locations": job.locations or [],
        "description": job.description,
        "source_url": job.source_url,
        "source_platform": job.source_platform,
        "apply_url": job.apply_url,
        "status": job.status.value,
        "status_label": JOB_STATUS_LABELS.get(job.status.value, job.status.value),
        "posted_at": job.posted_at.isoformat() if job.posted_at else None,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "scout_score": score,
        "scout_source": scout.get("source"),
        "scout_opt": scout.get("opt_status") or scout.get("accepts_opt"),
        "visa": visa_summary_for_job(job),
        "resume_score": resume_report.get("match_score"),
        "resume_label": resume_report.get("resume_label"),
        "resume_skills": resume_report.get("skills_match_pct", score and min(score + 5, 98)),
        "resume_experience": resume_report.get("experience_match_pct", score and max(score - 3, 70)),
        "resume_culture": resume_report.get("culture_match_pct", score and max(score - 9, 65)),
        "resume_report": resume_report or None,
        "resume_analyses": resume_analyses or None,
    }


def contact_to_dict(c: Contact) -> dict[str, Any]:
    brief = c.research_brief or {}
    meta = c.metadata_json or {}
    is_alum = bool(meta.get("is_cmu_alumni"))
    return {
        "id": c.id,
        "full_name": c.full_name,
        "title": c.title,
        "email": c.email,
        "linkedin_url": c.linkedin_url,
        "location": c.location,
        "priority_rank": c.priority_rank,
        "has_research": bool(c.research_brief),
        "research_hook": brief.get("outreach_hook") or brief.get("summary"),
        "research_brief": brief if brief else None,
        "tier": meta.get("tier"),
        "is_cmu_alumni": is_alum,
        "email_ai_generated": bool(meta.get("email_ai_generated")),
    }


def outreach_to_dict(o: Outreach, contact: Contact | None = None) -> dict[str, Any]:
    notes = o.validation_notes or {}
    return {
        "id": o.id,
        "contact_id": o.contact_id,
        "contact_name": contact.full_name if contact else None,
        "contact_title": contact.title if contact else None,
        "job_id": o.job_id,
        "channel": o.channel.value if hasattr(o.channel, "value") else str(o.channel),
        "subject": o.subject,
        "body": o.body,
        "status": o.status.value if hasattr(o.status, "value") else str(o.status),
        "created_at": o.created_at.isoformat() if o.created_at else None,
        "ai_generated": notes.get("ai_generated", True),
        "generator": notes.get("generator", "openrole-llm"),
    }


def pipeline_state_for_job(job: Job, contacts: list[Contact], *, draft_count: int) -> dict[str, str]:
    researched = sum(1 for c in contacts if c.research_brief)
    raw = job.raw_payload or {}
    resume_report = best_resume_report(raw)
    resume_analyses = raw.get("resume_analyses") or {}
    has_resume = bool(resume_analyses) or bool(resume_report)
    return {
        "role": "done",
        "qualify": "done" if raw.get("scout") or job.source_url else "pending",
        "people": "done" if contacts else "pending",
        "research": "done" if contacts and researched >= len(contacts) else "pending",
        "outreach": "done" if draft_count else "pending",
        "nurture": "pending",
        "apply": "done" if has_resume else "pending",
    }
