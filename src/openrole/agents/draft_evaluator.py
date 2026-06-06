"""Evaluator-optimizer loop for outreach drafts (LangGraph evaluator pattern)."""

from __future__ import annotations

import json
import re
from typing import Any, Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from openrole.agents.email_writer import EmailWriterError, _generate_drafts
from openrole.db.models import Contact, Job
from openrole.db.repository import save_outreach_draft
from openrole.db.session import session_scope
from openrole.llm.vertex import get_chat_model
from openrole.tools.candidate_profile import load_candidate_profile


class DraftEvaluation(BaseModel):
    acceptable: bool
    grade: Literal["good", "needs_work"]
    feedback: str = ""
    email_score: int = Field(default=0, ge=0, le=100)
    linkedin_score: int = Field(default=0, ge=0, le=100)


def evaluate_drafts(
    *,
    email: dict[str, str | None],
    linkedin: dict[str, str | None],
    contact: Contact,
    job: Job,
    brief: dict[str, Any],
) -> DraftEvaluation:
    """Score outreach drafts; return structured feedback for regeneration."""
    try:
        model = get_chat_model(writing=False, temperature=0.1)
    except RuntimeError as exc:
        raise EmailWriterError(str(exc)) from exc

    context = {
        "contact": {"name": contact.full_name, "title": contact.title},
        "job": {
            "title": job.title,
            "company": contact.company.name if contact.company else None,
            "department": job.department,
        },
        "research_hook": brief.get("suggested_hook"),
        "email_subject": email.get("subject"),
        "email_body": email.get("body"),
        "linkedin_body": linkedin.get("body"),
        "criteria": [
            "Specific hook from research (not generic)",
            "Under length limits (email ~150 words, LinkedIn ~280 chars)",
            "Professional human tone, no corporate boilerplate",
            "Clear ask without being pushy",
            "No placeholders or invented facts",
        ],
    }
    system = (
        "You evaluate cold outreach drafts for technical job seekers. "
        "Return ONLY JSON: "
        '{"acceptable": bool, "grade": "good"|"needs_work", "feedback": "actionable", '
        '"email_score": 0-100, "linkedin_score": 0-100}. '
        "acceptable=true only if both drafts would plausibly get a reply from this contact."
    )
    response = model.invoke(
        [SystemMessage(content=system), HumanMessage(content=json.dumps(context)[:50_000])]
    )
    data = _parse_json(str(response.content))
    return DraftEvaluation(
        acceptable=bool(data.get("acceptable")),
        grade="good" if data.get("grade") == "good" else "needs_work",
        feedback=str(data.get("feedback") or ""),
        email_score=int(data.get("email_score") or 0),
        linkedin_score=int(data.get("linkedin_score") or 0),
    )


def draft_outreach_optimized(
    *,
    contact_id: str,
    job_id: str,
    max_iterations: int = 3,
) -> dict[str, Any]:
    """Generate, evaluate, and refine outreach drafts until acceptable or max iterations."""
    with session_scope() as session:
        contact = session.get(Contact, contact_id)
        job = session.get(Job, job_id)
        if contact is None or job is None:
            raise EmailWriterError("Contact or job not found")
        if not contact.research_brief:
            raise EmailWriterError("Run research on this contact first.")

        profile = load_candidate_profile()
        brief = contact.research_brief
        feedback: str | None = None
        last_eval: DraftEvaluation | None = None
        payloads: dict[str, dict[str, str | None]] = {}

        for attempt in range(1, max_iterations + 1):
            payloads = _generate_drafts(
                contact=contact,
                job=job,
                brief=brief,
                profile=profile,
                revision_feedback=feedback,
            )
            last_eval = evaluate_drafts(
                email=payloads.get("email") or {},
                linkedin=payloads.get("linkedin") or {},
                contact=contact,
                job=job,
                brief=brief,
            )
            if last_eval.acceptable:
                break
            feedback = last_eval.feedback

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
        eval_dict = last_eval.model_dump() if last_eval else {}
        eval_dict["attempts"] = attempt
        eval_dict["contact_id"] = contact_id
        return {
            "status": "ok",
            "contact_id": contact_id,
            "drafts": saved,
            "evaluation": eval_dict,
            "profile_warnings": profile.get("warnings") or [],
        }


def _parse_json(content: str) -> dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    data = json.loads(text)
    if not isinstance(data, dict):
        raise EmailWriterError("Evaluator returned invalid JSON")
    return data
