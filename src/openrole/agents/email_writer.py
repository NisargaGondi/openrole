"""Draft cold email and LinkedIn notes from research briefs."""

from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from openrole.db.models import Contact, Job
from openrole.db.repository import save_outreach_draft
from openrole.db.session import session_scope
from openrole.llm.vertex import get_chat_model
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
        payloads = _generate_drafts(
            contact=contact,
            job=job,
            brief=contact.research_brief,
            profile=profile,
        )
        saved = []
        for channel, draft in payloads.items():
            row = save_outreach_draft(
                session,
                contact_id=contact_id,
                job_id=job_id,
                channel=channel,
                subject=draft.get("subject"),
                body=draft.get("body") or "",
            )
            saved.append({"id": row.id, "channel": channel})
        session.commit()
        return {"status": "ok", "drafts": saved, "profile_warnings": profile.get("warnings") or []}


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

    context = {
        "contact": {
            "name": contact.full_name,
            "title": contact.title,
            "email": contact.email,
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
            "resume_labels": [r.get("label") for r in profile.get("resumes") or []],
            "full_context": profile.get("prompt_context"),
        },
    }
    if revision_feedback:
        context["revision_feedback"] = revision_feedback
    system = (
        "Write personalized outreach drafts for a job seeker reaching out about a specific role. "
        "Use candidate_profile.full_context (resumes, GitHub, website, links) for accurate "
        "credentials and projects — do not invent experience not supported by that context. "
        "Reference something specific from the contact research when possible. "
        "Return ONLY JSON: "
        '{"email": {"subject": "...", "body": "..."}, '
        '"linkedin": {"subject": null, "body": "..."}}. '
        "Email under 150 words; LinkedIn connection note under 280 characters. "
        "No placeholders like [Your Name]. Sign off with the candidate's first name from profile."
    )
    if revision_feedback:
        system += " Revise the previous draft using revision_feedback — do not ignore it."
    response = model.invoke(
        [SystemMessage(content=system), HumanMessage(content=json.dumps(context)[:100_000])]
    )
    content = str(response.content).strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)
    data = json.loads(content)
    if not isinstance(data, dict):
        raise EmailWriterError("LLM returned invalid draft JSON")
    return {
        "email": data.get("email") or {},
        "linkedin": data.get("linkedin") or {},
    }
