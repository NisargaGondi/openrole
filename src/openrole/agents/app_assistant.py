"""Draft answers to written application questions for a saved job."""

from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import select

from openrole.db.models import Application, Job
from openrole.db.repository import save_application_draft, sync_resumes_from_env
from openrole.db.session import session_scope
from openrole.llm import get_chat_model
from openrole.schemas.application import ApplicationAnswer, ApplicationDraft
from openrole.tools.candidate_profile import load_candidate_profile


class ApplicationAssistantError(Exception):
    pass


def draft_application_answers(
    *,
    job_id: str,
    questions: list[str],
    resume_label: str | None = None,
) -> dict[str, Any]:
    """Generate draft answers for application form questions; persist on Application row."""
    cleaned = [q.strip() for q in questions if q and q.strip()]
    if not cleaned:
        raise ApplicationAssistantError("Provide at least one application question.")

    with session_scope() as session:
        job = session.get(Job, job_id)
        if job is None:
            raise ApplicationAssistantError("Job not found")

        resumes = sync_resumes_from_env(session)
        chosen = resumes[0] if resumes else None
        if resume_label and resumes:
            for r in resumes:
                if r.label == resume_label:
                    chosen = r
                    break

        profile = load_candidate_profile(fetch_links=True)
        resume_text = (chosen.content_text or "") if chosen else ""
        if not resume_text and profile.get("resumes"):
            resume_text = profile["resumes"][0].get("text") or ""

        draft = _generate_answers(
            job=job,
            questions=cleaned,
            resume_label=chosen.label if chosen else None,
            resume_text=resume_text,
            profile=profile,
        )
        app_row = save_application_draft(
            session,
            job_id=job_id,
            resume_id=chosen.id if chosen else None,
            answers_json=draft.to_answers_json(),
        )
        session.commit()
        return {
            "status": "ok",
            "application_id": app_row.id,
            "draft": draft.to_db_dict(),
            "profile_warnings": profile.get("warnings") or [],
        }


def get_application_draft(job_id: str) -> dict[str, Any] | None:
    with session_scope() as session:
        row = session.scalar(
            select(Application).where(Application.job_id == job_id).order_by(Application.created_at.desc())
        )
        if row is None or not row.answers_json:
            return None
        return row.answers_json


def _generate_answers(
    *,
    job: Job,
    questions: list[str],
    resume_label: str | None,
    resume_text: str,
    profile: dict[str, Any],
) -> ApplicationDraft:
    try:
        model = get_chat_model(writing=True, temperature=0.35)
    except RuntimeError as exc:
        raise ApplicationAssistantError(str(exc)) from exc

    context = {
        "job": {
            "title": job.title,
            "company": job.company.name if job.company else None,
            "department": job.department,
            "locations": job.locations,
            "description": (job.description or "")[:12000],
        },
        "questions": questions,
        "resume_label": resume_label,
        "resume_text": resume_text[:10000],
        "candidate_context": profile.get("prompt_context"),
    }
    system = (
        "Draft application form answers for a job seeker. Use only facts from resume and "
        "candidate_context — do not invent employers, dates, or projects. "
        "Write in first person, professional but human (not corporate boilerplate). "
        "Return ONLY JSON: "
        '{"answers": [{"question": "...", "answer": "...", "notes": "optional reviewer note"}], '
        '"tone_notes": "short guidance for the candidate"}. '
        "Each answer should directly address the question; typical length 80-200 words unless "
        "the question asks for brevity."
    )
    response = model.invoke(
        [SystemMessage(content=system), HumanMessage(content=json.dumps(context)[:100_000])]
    )
    data = _parse_json(str(response.content))
    answers = [
        ApplicationAnswer(
            question=str(a.get("question") or questions[i] if i < len(questions) else ""),
            answer=str(a.get("answer") or ""),
            notes=a.get("notes"),
        )
        for i, a in enumerate(data.get("answers") or [])
    ]
    if len(answers) < len(questions):
        for q in questions[len(answers) :]:
            answers.append(ApplicationAnswer(question=q, answer="", notes="Generation incomplete"))
    return ApplicationDraft(
        job_id=job.id,
        resume_label=resume_label,
        answers=answers,
        tone_notes=str(data.get("tone_notes") or ""),
    )


def _parse_json(content: str) -> dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ApplicationAssistantError("LLM returned invalid application JSON")
    return data
