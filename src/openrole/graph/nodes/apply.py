"""Apply-stage nodes: resume optimization and application Q&A workers."""

from __future__ import annotations

from openrole.agents.app_assistant import ApplicationAssistantError, draft_application_answers
from openrole.agents.resume_optimizer import ResumeOptimizerError, optimize_resume_for_job
from openrole.graph.state import AppAnswerWorkerState, OpenRoleState
from openrole.schemas.pipeline import PipelineOptions


def optimize_resume_node(state: OpenRoleState) -> dict:
    job_id = state.get("job_id")
    if not job_id:
        return {"errors": ["job_id required for resume optimization"]}
    opts = PipelineOptions.from_state(state.get("pipeline_options"))
    try:
        result = optimize_resume_for_job(job_id=job_id, resume_label=opts.resume_label)
        report = result.get("report") or {}
        return {
            "resume_report": report,
            "pipeline_stage": "resume_analyzed",
            "stages_completed": ["optimize_resume"],
            "warnings": result.get("profile_warnings") or [],
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
