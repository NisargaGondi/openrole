"""Apply-stage nodes: resume optimization and application Q&A workers."""

from __future__ import annotations

from openrole.agents.app_assistant import ApplicationAssistantError, draft_application_answers
from openrole.agents.resume_optimizer import (
    ResumeOptimizerError,
    optimize_all_resumes_for_job,
    optimize_resume_for_job,
)
from openrole.graph.state import AppAnswerWorkerState, OpenRoleState
from openrole.schemas.pipeline import PipelineOptions


def _resolve_resume_targets(opts: PipelineOptions) -> str | list[str | None]:
    if opts.resume_labels:
        if len(opts.resume_labels) == 1 and opts.resume_labels[0] == "__all__":
            return "__all__"
        return list(opts.resume_labels)
    if opts.resume_label == "__all__":
        return "__all__"
    if opts.resume_label:
        return [opts.resume_label]
    return [None]


def optimize_resume_node(state: OpenRoleState) -> dict:
    job_id = state.get("job_id")
    if not job_id:
        return {"errors": ["job_id required for resume optimization"]}
    opts = PipelineOptions.from_state(state.get("pipeline_options"))
    targets = _resolve_resume_targets(opts)
    warnings: list[str] = []
    errors: list[str] = []

    try:
        if targets == "__all__":
            result = optimize_all_resumes_for_job(job_id=job_id)
            reports = result.get("reports") or []
            warnings.extend(result.get("warnings") or [])
        else:
            reports = []
            for label in targets:
                try:
                    out = optimize_resume_for_job(job_id=job_id, resume_label=label)
                    reports.append(out.get("report") or {})
                    warnings.extend(out.get("profile_warnings") or [])
                except ResumeOptimizerError as exc:
                    errors.append(str(exc))

        if not reports:
            return {
                "errors": errors or ["No resume analysis completed"],
                "pipeline_stage": "resume_failed",
            }

        best = max(reports, key=lambda r: int(r.get("match_score") or 0))
        return {
            "resume_report": best,
            "resume_analyses": {r.get("resume_label") or "default": r for r in reports},
            "pipeline_stage": "resume_analyzed",
            "stages_completed": ["optimize_resume"],
            "warnings": warnings,
            **({"errors": errors} if errors else {}),
        }
    except ResumeOptimizerError as exc:
        return {"errors": [str(exc)], "pipeline_stage": "resume_failed"}


def prepare_application_node(state: OpenRoleState) -> dict:
    opts = PipelineOptions.from_state(state.get("pipeline_options"))
    questions = opts.application_questions
    if not questions:
        return {"application_questions": [], "pipeline_stage": "application_skipped"}
    return {
        "application_questions": questions,
        "pipeline_stage": "application_prepared",
        "stages_completed": ["prepare_application"],
    }


def app_answer_worker_node(state: AppAnswerWorkerState) -> dict:
    job_id = state.get("job_id")
    question = state.get("question")
    if not job_id or not question:
        return {"errors": ["app_answer_worker missing job_id or question"]}
    try:
        result = draft_application_answers(
            job_id=job_id,
            questions=[question],
            resume_label=state.get("resume_label"),
        )
        draft = result.get("draft") or {}
        answers = draft.get("answers") or []
        answer_text = answers[0].get("answer") if answers else ""
        return {
            "application_answers": [{"question": question, "answer": answer_text}],
            "warnings": result.get("profile_warnings") or [],
            "stages_completed": [f"app_q:{question[:40]}"],
        }
    except ApplicationAssistantError as exc:
        return {"errors": [f"Q '{question[:50]}': {exc}"]}


def finalize_application_node(state: OpenRoleState) -> dict:
    """Merge parallel app answers into application_draft shape."""
    answers = state.get("application_answers") or []
    if not answers:
        return {"pipeline_stage": "application_empty"}
    return {
        "application_draft": {
            "answers": answers,
            "job_id": state.get("job_id"),
        },
        "pipeline_stage": "application_drafted",
        "stages_completed": ["finalize_application"],
    }
