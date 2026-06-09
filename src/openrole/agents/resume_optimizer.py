"""Compare candidate resume(s) against a job description — ATS gaps and edit suggestions."""

from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from openrole.db.models import Job
from openrole.db.repository import save_job_resume_analysis, sync_resumes_from_env
from openrole.db.session import session_scope
from openrole.llm import get_chat_model
from openrole.schemas.resume_analysis import ResumeEditSuggestion, ResumeOptimizationReport
from openrole.tools.candidate_profile import load_candidate_profile


class ResumeOptimizerError(Exception):
    pass


def optimize_resume_for_job(
    *,
    job_id: str,
    resume_label: str | None = None,
) -> dict[str, Any]:
    """Analyze one resume against a saved job; persist report on the job."""
    with session_scope() as session:
        job = session.get(Job, job_id)
        if job is None:
            raise ResumeOptimizerError("Job not found")
        if not job.description:
            raise ResumeOptimizerError("Job has no description — re-ingest or paste the JD.")

        resumes = sync_resumes_from_env(session)
        session.commit()
        if not resumes:
            raise ResumeOptimizerError(
                "No resumes configured. Set CANDIDATE_RESUME_PATHS in .env "
                "(comma-separated .pdf/.md/.txt paths)."
            )

        chosen = _pick_resume(resumes, resume_label)
        if chosen is None:
            labels = ", ".join(r.label for r in resumes)
            raise ResumeOptimizerError(f"Resume not found. Available: {labels}")

        text = chosen.content_text or ""
        if not text.strip():
            raise ResumeOptimizerError(f"Resume `{chosen.label}` has no extractable text.")

        profile = load_candidate_profile(fetch_links=True)
        report = _analyze_with_llm(job=job, resume_label=chosen.label, resume_text=text, profile=profile)
        report = report.model_copy(
            update={
                "job_id": job_id,
                "resume_label": chosen.label,
                "resume_path": chosen.file_path,
            }
        )
        save_job_resume_analysis(session, job_id=job_id, report=report.to_db_dict())
        session.commit()
        return {"status": "ok", "report": report.to_db_dict(), "profile_warnings": profile.get("warnings")}


def optimize_all_resumes_for_job(job_id: str) -> dict[str, Any]:
    """Run optimization for every configured resume; useful when holding multiple variants."""
    with session_scope() as session:
        resumes = sync_resumes_from_env(session)
        session.commit()
    if not resumes:
        raise ResumeOptimizerError("No resumes in CANDIDATE_RESUME_PATHS.")

    reports = []
    warnings: list[str] = []
    for resume in resumes:
        try:
            out = optimize_resume_for_job(job_id=job_id, resume_label=resume.label)
            reports.append(out["report"])
            warnings.extend(out.get("profile_warnings") or [])
        except ResumeOptimizerError as exc:
            warnings.append(f"{resume.label}: {exc}")
    if not reports:
        raise ResumeOptimizerError("; ".join(warnings) or "No reports generated.")
    return {"status": "ok", "reports": reports, "warnings": warnings}


def get_job_resume_analyses(job_id: str) -> dict[str, Any]:
    with session_scope() as session:
        job = session.get(Job, job_id)
        if job is None:
            raise ResumeOptimizerError("Job not found")
        payload = job.raw_payload or {}
        return payload.get("resume_analyses") or {}


def _pick_resume(resumes, resume_label: str | None):
    if not resume_label:
        default = next((r for r in resumes if r.is_default), None)
        return default or resumes[0]
    for r in resumes:
        if r.label == resume_label or (r.file_path and r.file_path.endswith(resume_label)):
            return r
    return None


def _analyze_with_llm(
    *,
    job: Job,
    resume_label: str,
    resume_text: str,
    profile: dict[str, Any],
) -> ResumeOptimizationReport:
    try:
        model = get_chat_model(writing=True, temperature=0.2)
    except RuntimeError as exc:
        raise ResumeOptimizerError(str(exc)) from exc

    context = {
        "job": {
            "title": job.title,
            "company": job.company.name if job.company else None,
            "department": job.department,
            "locations": job.locations,
            "description": (job.description or "")[:15000],
        },
        "resume_label": resume_label,
        "resume_text": resume_text[:12000],
        "candidate_links": {
            "linkedin": profile.get("linkedin_url"),
            "github": profile.get("github_url"),
            "website": profile.get("website_url"),
            "github_summary": profile.get("github_summary"),
        },
        "profile_notes": profile.get("profile_notes"),
    }
    system = (
        "You are an expert resume coach for technical roles (ML/AI, security, SWE). "
        "Compare the resume to the job description. Return ONLY valid JSON with keys: "
        "match_score (0-100 int), summary (string), strengths (array of strings), "
        "gaps (array), missing_keywords (array of ATS-relevant terms from JD missing on resume), "
        "ats_risks (array — formatting/keyword issues), "
        "suggested_edits (array of {section, issue, suggestion}), "
        "recommended_resume (null or string — if multiple variants exist, which to use). "
        "Be specific and actionable. Do not invent experience not on the resume."
    )
    response = model.invoke(
        [SystemMessage(content=system), HumanMessage(content=json.dumps(context)[:100_000])]
    )
    data = _parse_json(str(response.content))
    edits = [
        ResumeEditSuggestion(**e) if isinstance(e, dict) else ResumeEditSuggestion(suggestion=str(e))
        for e in data.get("suggested_edits") or []
    ]
    return ResumeOptimizationReport(
        job_id=job.id,
        resume_label=resume_label,
        match_score=int(data.get("match_score") or 0),
        summary=str(data.get("summary") or ""),
        strengths=list(data.get("strengths") or []),
        gaps=list(data.get("gaps") or []),
        missing_keywords=list(data.get("missing_keywords") or []),
        ats_risks=list(data.get("ats_risks") or []),
        suggested_edits=edits,
        recommended_resume=data.get("recommended_resume"),
    )


def _parse_json(content: str) -> dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ResumeOptimizerError("LLM returned invalid analysis JSON")
    return data
