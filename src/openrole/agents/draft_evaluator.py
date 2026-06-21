"""Evaluator-optimizer loop for outreach drafts (LangGraph evaluator pattern)."""

from __future__ import annotations

import json
import re
from typing import Any, Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from openrole.agents.email_writer import EmailWriterError, _generate_drafts
from openrole.agents.outreach_prompts import (
    build_evaluator_system_prompt,
    evaluation_criteria_for_tier,
    get_tier_template,
    resolve_contact_tier,
    tier_label,
)
from openrole.schemas.contact import ContactTier
from openrole.db.models import Contact, Job
from openrole.db.repository import save_outreach_draft
from openrole.db.session import session_scope
from openrole.config import get_settings
from openrole.llm import get_chat_model
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

    settings = get_settings()
    tier = resolve_contact_tier(contact)
    research_angles = list(brief.get("outreach_angles") or [])
    context = {
        "contact": {
            "name": contact.full_name,
            "title": contact.title,
            "tier": tier.name,
            "tier_label": tier_label(tier),
        },
        "job": {
            "title": job.title,
            "company": contact.company.name if contact.company else None,
            "department": job.department,
        },
        "research_primary_hook": brief.get("suggested_hook"),
        "research_summary": brief.get("summary"),
        "research_angles": research_angles[:3],
        "email_subject": email.get("subject"),
        "email_body": email.get("body"),
        "email_word_count": len(str(email.get("body") or "").split()),
        "linkedin_body": linkedin.get("body"),
        "linkedin_char_count": len(str(linkedin.get("body") or "")),
        "criteria": evaluation_criteria_for_tier(
            tier,
            graduation=settings.candidate_graduation,
            role_search=settings.candidate_role_search,
        ),
    }
    system = build_evaluator_system_prompt(tier=tier)
    response = model.invoke(
        [SystemMessage(content=system), HumanMessage(content=json.dumps(context)[:50_000])]
    )
    data = _parse_json(str(response.content))
    evaluation = DraftEvaluation(
        acceptable=bool(data.get("acceptable")),
        grade="good" if data.get("grade") == "good" else "needs_work",
        feedback=str(data.get("feedback") or ""),
        email_score=int(data.get("email_score") or 0),
        linkedin_score=int(data.get("linkedin_score") or 0),
    )
    return _apply_hard_gates(
        evaluation,
        tier=tier,
        email_body=str(email.get("body") or ""),
        linkedin_body=str(linkedin.get("body") or ""),
    )


def _apply_hard_gates(
    evaluation: DraftEvaluation,
    *,
    tier: ContactTier,
    email_body: str,
    linkedin_body: str,
) -> DraftEvaluation:
    """Enforce non-negotiable length/tier rules after LLM scoring."""
    feedback_parts: list[str] = []
    acceptable = evaluation.acceptable
    email_words = len(email_body.split())
    linkedin_chars = len(linkedin_body)

    if tier == ContactTier.EXECUTIVE and email_words > 120:
        acceptable = False
        feedback_parts.append(
            f"Email is {email_words} words; executive tier must be under ~100 words. "
            "Shorten to a routing ask — who owns hiring for this role?"
        )

    template = get_tier_template(tier)
    linkedin_limit = 280
    if linkedin_chars > linkedin_limit:
        acceptable = False
        feedback_parts.append(
            f"LinkedIn note is {linkedin_chars} characters; max {linkedin_limit}. "
            f"Trim to a {template.get('linkedin_chars', '250-280')} connection note."
        )

    if not feedback_parts:
        return evaluation

    merged_feedback = " ".join(feedback_parts)
    if evaluation.feedback:
        merged_feedback = f"{merged_feedback} {evaluation.feedback}"

    return DraftEvaluation(
        acceptable=acceptable,
        grade="needs_work",
        feedback=merged_feedback.strip(),
        email_score=min(evaluation.email_score, 70 if tier == ContactTier.EXECUTIVE and email_words > 120 else evaluation.email_score),
        linkedin_score=min(
            evaluation.linkedin_score,
            70 if linkedin_chars > linkedin_limit else evaluation.linkedin_score,
        ),
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
