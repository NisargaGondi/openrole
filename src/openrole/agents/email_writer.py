"""Draft cold email and LinkedIn notes from research briefs."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from openrole.db.models import Contact, Job
from openrole.db.repository import save_outreach_draft
from openrole.db.session import session_scope
from openrole.agents.outreach_prompts import (
    build_draft_system_prompt,
    resolve_contact_tier,
    tier_label,
)
from openrole.llm import get_chat_model
from openrole.llm.parse import LLMJSONError, extract_llm_text, parse_json_object
from openrole.tools.candidate_profile import load_candidate_profile


class EmailWriterError(Exception):
    pass


def draft_outreach_for_contact(*, contact_id: str, job_id: str) -> dict[str, Any]:
    with session_scope() as session:
        contact = session.get(Contact, contact_id)
        job = session.get(Job, job_id)
        if contact is None or job is None:
            raise EmailWriterError("Contact or job not found")
        if not contact.research_brief:
            raise EmailWriterError("Run research on this contact first.")

        profile = load_candidate_profile()
        saved = _save_drafts_for_contact(
            session,
            contact=contact,
            job=job,
            brief=contact.research_brief,
            profile=profile,
        )
        session.commit()
        return {"status": "ok", "drafts": saved, "profile_warnings": profile.get("warnings") or []}


def draft_outreach_for_job(*, job_id: str, auto_research: bool = True) -> dict[str, Any]:
    """Research (if needed) and draft outreach for every contact found for this job."""
    from openrole.agents.person_research import build_research_brief
    from openrole.db.repository import list_contacts_for_job, save_research_brief

    profile = load_candidate_profile()
    drafted: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    errors: list[dict[str, str]] = []

    with session_scope() as session:
        job = session.get(Job, job_id)
        if job is None or not job.company_id:
            raise EmailWriterError("Job not found")
        contacts = list_contacts_for_job(
            session,
            company_id=job.company_id,
            source_job_id=job_id,
        )
        if not contacts:
            raise EmailWriterError("No contacts for this job — run **Find people** on the Jobs tab.")

        for contact in contacts:
            try:
                if not contact.research_brief:
                    if not auto_research:
                        skipped.append(
                            {
                                "contact_id": contact.id,
                                "name": contact.full_name,
                                "reason": "no research brief",
                            }
                        )
                        continue
                    company_name = contact.company.name if contact.company else "Unknown"
                    brief = build_research_brief(
                        contact=contact,
                        job=job,
                        company_name=company_name,
                    )
                    save_research_brief(session, contact.id, brief.to_db_dict())
                    session.refresh(contact)

                saved = _save_drafts_for_contact(
                    session,
                    contact=contact,
                    job=job,
                    brief=contact.research_brief or {},
                    profile=profile,
                )
                drafted.append(
                    {
                        "contact_id": contact.id,
                        "full_name": contact.full_name,
                        "drafts": saved,
                    }
                )
            except Exception as exc:
                errors.append(
                    {
                        "contact_id": contact.id,
                        "name": contact.full_name,
                        "error": str(exc),
                    }
                )

        session.commit()

    return {
        "status": "ok" if drafted and not errors else ("partial" if drafted else "failed"),
        "contact_count": len(contacts),
        "drafted_count": len(drafted),
        "drafted": drafted,
        "skipped": skipped,
        "errors": errors,
        "profile_warnings": profile.get("warnings") or [],
    }


def _save_drafts_for_contact(
    session,
    *,
    contact: Contact,
    job: Job,
    brief: dict[str, Any],
    profile: dict[str, Any],
) -> list[dict[str, str]]:
    payloads = _generate_drafts(
        contact=contact,
        job=job,
        brief=brief,
        profile=profile,
    )
    saved: list[dict[str, str]] = []
    for channel, draft in payloads.items():
        row = save_outreach_draft(
            session,
            contact_id=contact.id,
            job_id=job.id,
            channel=channel,
            subject=draft.get("subject"),
            body=draft.get("body") or "",
        )
        saved.append({"id": row.id, "channel": channel})
    return saved


def load_user_profile() -> dict[str, Any]:
    """Backward-compatible alias for draft writers."""
    return load_candidate_profile()


def _generate_drafts(
    *,
    contact: Contact,
    job: Job,
    brief: dict[str, Any],
    profile: dict[str, Any],
    revision_feedback: str | None = None,
) -> dict[str, dict[str, str | None]]:
    try:
        model = get_chat_model(writing=True, temperature=0.4)
    except RuntimeError as exc:
        raise EmailWriterError(str(exc)) from exc

    tier = resolve_contact_tier(contact)
    context = {
        "contact": {
            "name": contact.full_name,
            "title": contact.title,
            "email": contact.email,
            "tier": tier.name,
            "tier_label": tier_label(tier),
            "priority_reason": contact.priority_reason,
        },
        "job": {
            "title": job.title,
            "company": contact.company.name if contact.company else None,
            "department": job.department,
            "locations": job.locations,
            "description_excerpt": (job.description or "")[:3000],
        },
        "research": brief,
        "candidate_profile": {
            "name": profile.get("name"),
            "linkedin_url": profile.get("linkedin_url"),
            "github_url": profile.get("github_url"),
            "website_url": profile.get("website_url"),
            "graduation": profile.get("graduation"),
            "role_search": profile.get("role_search"),
            "resume_labels": [r.get("label") for r in profile.get("resumes") or []],
            "full_context": profile.get("prompt_context"),
        },
    }
    if revision_feedback:
        context["revision_feedback"] = revision_feedback
    system = build_draft_system_prompt(
        tier=tier,
        revision_feedback=revision_feedback,
        graduation=profile.get("graduation"),
        role_search=profile.get("role_search"),
    )
    user_content = json.dumps(context)[:100_000]
    messages = [SystemMessage(content=system), HumanMessage(content=user_content)]
    last_error: str | None = None

    for attempt in range(2):
        response = model.invoke(messages)
        try:
            data = parse_json_object(extract_llm_text(response), error_label="Draft writer")
            break
        except LLMJSONError as exc:
            last_error = str(exc)
            if attempt == 0:
                messages.append(
                    HumanMessage(
                        content=(
                            "Your previous reply was not valid JSON. Return ONLY a single JSON "
                            'object with keys "email" and "linkedin" — no markdown, no prose.'
                        )
                    )
                )
                continue
            raise EmailWriterError(last_error) from exc
    else:
        raise EmailWriterError(last_error or "Draft writer returned invalid JSON")

    if not isinstance(data, dict):
        raise EmailWriterError("LLM returned invalid draft JSON")
    return {
        "email": data.get("email") or {},
        "linkedin": data.get("linkedin") or {},
    }
