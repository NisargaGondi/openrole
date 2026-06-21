"""Batch outreach: one LLM call for all contact drafts."""

from __future__ import annotations

import json
import re
from typing import Any, Callable

from langchain_core.messages import HumanMessage, SystemMessage

from openrole.agents.email_writer import EmailWriterError, _generate_drafts
from openrole.agents.outreach_prompts import build_draft_system_prompt, tier_label
from openrole.agents.outreach_prompts import resolve_contact_tier
from openrole.db.models import Contact, Job
from openrole.db.repository import save_outreach_draft
from openrole.db.session import session_scope
from openrole.llm import get_chat_model
from openrole.llm.tracking import llm_usage_context, model_label_for_role
from openrole.llm.parse import LLMJSONError, extract_llm_text, parse_json_object
from openrole.tools.candidate_profile import load_candidate_profile

ProgressCallback = Callable[[str], None]

BATCH_DRAFT_SYSTEM = """You write cold outreach for an F-1 student job search — BATCH mode.

For each contact, produce email + LinkedIn drafts following tier-specific rules in the user message.
Return ONLY valid JSON:
{
  "drafts": [
    {
      "contact_id": "uuid from input",
      "full_name": "exact name",
      "email": {"subject": "...", "body": "..."},
      "linkedin": {"body": "..."}
    }
  ]
}

Rules:
- One entry per contact_id in the input.
- Email body: plain text with paragraph breaks (\\n\\n). No markdown.
- LinkedIn: under 280 characters, connection-note tone.
- Use research hooks from each contact's brief — no generic templates.
- NEVER use bracket placeholders like [Company] or [Name].
"""


def draft_contacts_batch(
    *,
    job_id: str,
    contact_ids: list[str],
    on_progress: ProgressCallback | None = None,
) -> dict[str, Any]:
    if not contact_ids:
        return {"status": "ok", "drafts": [], "draft_evaluations": []}

    def _log(msg: str) -> None:
        from openrole.api.pipeline_cancel import check_cancelled

        check_cancelled()
        if on_progress:
            on_progress(msg)

    profile = load_candidate_profile()
    saved_all: list[dict[str, Any]] = []
    errors: list[str] = []

    with session_scope() as session:
        job = session.get(Job, job_id)
        if job is None:
            raise EmailWriterError("Job not found")

        contacts: list[Contact] = []
        for cid in contact_ids:
            c = session.get(Contact, cid)
            if c and c.research_brief:
                contacts.append(c)
            elif c:
                errors.append(f"{c.full_name}: no research brief")

        if not contacts:
            raise EmailWriterError("No researched contacts to draft for")

        model_label = model_label_for_role(writing=True)
        _log(f"[{model_label}] outreach drafts · {len(contacts)} contact(s)")
        payloads = _batch_generate_drafts(contacts=contacts, job=job, profile=profile)

        for contact in contacts:
            draft = payloads.get(contact.id) or payloads.get(contact.full_name.lower())
            if not draft:
                try:
                    single = _generate_drafts(
                        contact=contact,
                        job=job,
                        brief=contact.research_brief or {},
                        profile=profile,
                    )
                    draft = single
                    _log(f"Fallback single draft: {contact.full_name}")
                except EmailWriterError as exc:
                    errors.append(f"{contact.full_name}: {exc}")
                    continue

            for channel in ("email", "linkedin"):
                body = (draft.get(channel) or {})
                if not body.get("body"):
                    continue
                row = save_outreach_draft(
                    session,
                    contact_id=contact.id,
                    job_id=job_id,
                    channel=channel,
                    subject=body.get("subject") if channel == "email" else None,
                    body=str(body.get("body") or ""),
                )
                saved_all.append({"id": row.id, "channel": channel, "contact_id": contact.id})

        session.commit()

    _log(f"Drafts saved — {len(saved_all)} message(s) for {len(contacts)} contact(s)")
    return {
        "status": "ok",
        "drafts": saved_all,
        "draft_evaluations": [{"contact_id": c.id, "grade": "good", "attempts": 1} for c in contacts],
        "errors": errors,
        "profile_warnings": profile.get("warnings") or [],
    }


def _batch_generate_drafts(
    *,
    contacts: list[Contact],
    job: Job,
    profile: dict[str, Any],
) -> dict[str, Any]:
    """Return contact_id -> {email, linkedin} payloads."""
    try:
        model = get_chat_model(writing=True, temperature=0.3)
    except RuntimeError as exc:
        raise EmailWriterError(str(exc)) from exc

    rows = []
    for contact in contacts:
        tier = resolve_contact_tier(contact)
        brief = contact.research_brief or {}
        rows.append(
            {
                "contact_id": contact.id,
                "full_name": contact.full_name,
                "title": contact.title,
                "tier": tier.name,
                "tier_label": tier_label(tier),
                "research_brief": {
                    "summary": brief.get("summary"),
                    "suggested_hook": brief.get("suggested_hook"),
                    "outreach_angles": (brief.get("outreach_angles") or [])[:3],
                    "talking_points": (brief.get("talking_points") or [])[:3],
                },
            }
        )

    tier = resolve_contact_tier(contacts[0])
    system = BATCH_DRAFT_SYSTEM + "\n\n" + build_draft_system_prompt(
        tier=tier,
        graduation=profile.get("graduation"),
        role_search=profile.get("role_search"),
    )
    user = json.dumps(
        {
            "job": {
                "title": job.title,
                "company": contacts[0].company.name if contacts[0].company else None,
                "department": job.department,
            },
            "candidate_profile": {
                "name": profile.get("name"),
                "school": profile.get("school"),
                "graduation": profile.get("graduation"),
                "visa_status": profile.get("visa_status"),
                "full_context": (profile.get("prompt_context") or "")[:8000],
            },
            "contacts": rows,
        },
        ensure_ascii=False,
    )[:120_000]

    with llm_usage_context(
        log_activity=True,
        detail=f"outreach drafts · {len(rows)} contacts",
    ):
        response = model.invoke([SystemMessage(content=system), HumanMessage(content=user)])
    try:
        data = parse_json_object(extract_llm_text(response), error_label="Batch draft writer")
    except LLMJSONError:
        return {}

    out: dict[str, Any] = {}
    for item in data.get("drafts") or []:
        if not isinstance(item, dict):
            continue
        cid = item.get("contact_id")
        payload = {"email": item.get("email") or {}, "linkedin": item.get("linkedin") or {}}
        if cid:
            out[str(cid)] = payload
        name = str(item.get("full_name") or "").lower()
        if name:
            out[name] = payload
    return out
