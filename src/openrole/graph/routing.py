"""Routing helpers for conditional edges."""

from __future__ import annotations

from typing import Literal

from openrole.graph.state import OpenRoleState
from openrole.schemas.pipeline import PipelineOptions


def pipeline_options(state: OpenRoleState) -> PipelineOptions:
    return PipelineOptions.from_state(state.get("pipeline_options"))


def route_entry(state: OpenRoleState) -> Literal["ingest", "route_existing"]:
    if state.get("job_id"):
        return "route_existing"
    return "ingest"


def route_after_ingest(state: OpenRoleState) -> Literal["route_existing", "finalize"]:
    if state.get("errors") and not state.get("job_id"):
        return "finalize"
    return "route_existing"


def route_existing_job(state: OpenRoleState) -> Literal[
    "extract_context",
    "prepare_outreach",
    "optimize_resume",
    "prepare_application",
    "finalize",
]:
    opts = pipeline_options(state)
    if opts.run_people:
        return "extract_context"
    if opts.run_research or opts.run_outreach:
        return "prepare_outreach"
    if opts.run_resume:
        return "optimize_resume"
    if opts.run_application and opts.application_questions:
        return "prepare_application"
    return "finalize"


def route_after_persist(state: OpenRoleState) -> Literal["prepare_outreach", "optimize_resume", "finalize"]:
    opts = pipeline_options(state)
    if state.get("errors") and not state.get("contact_count"):
        if opts.run_resume:
            return "optimize_resume"
        return "finalize"
    if opts.run_research or opts.run_outreach:
        return "prepare_outreach"
    if opts.run_resume:
        return "optimize_resume"
    return "finalize"


def route_after_outreach_workers(state: OpenRoleState) -> Literal["outreach_review", "finalize"]:
    opts = pipeline_options(state)
    if not opts.run_outreach:
        return "finalize"
    return "outreach_review"


def route_after_resume(state: OpenRoleState) -> Literal["application_review", "finalize"]:
    opts = pipeline_options(state)
    if opts.run_application and opts.application_questions:
        return "application_review"
    return "finalize"


def route_after_app_workers(state: OpenRoleState) -> Literal["finalize"]:
    return "finalize"


def dispatch_research(state: OpenRoleState):
    sends = should_dispatch_research(state)
    if sends:
        return sends
    return "skip_research"


def dispatch_drafts(state: OpenRoleState):
    sends = should_dispatch_drafts(state)
    if sends:
        return sends
    return "skip_drafts"


def dispatch_app_answers(state: OpenRoleState):
    sends = should_dispatch_app_answers(state)
    if sends:
        return sends
    return "skip_app_answers"


def should_dispatch_research(state: OpenRoleState) -> list:
    from langgraph.types import Send

    opts = pipeline_options(state)
    if not opts.run_research:
        return []
    ids = state.get("contact_ids") or []
    if not ids:
        return []
    return [Send("research_worker", {"job_id": state["job_id"], "contact_id": cid}) for cid in ids]


def should_dispatch_drafts(state: OpenRoleState) -> list:
    from langgraph.types import Send

    opts = pipeline_options(state)
    if not opts.run_outreach:
        return []
    ids = state.get("contact_ids") or []
    if not ids:
        return []
    return [
        Send(
            "draft_worker",
            {
                "job_id": state["job_id"],
                "contact_id": cid,
                "max_draft_iterations": opts.max_draft_iterations,
            },
        )
        for cid in ids
    ]


def should_dispatch_app_answers(state: OpenRoleState) -> list:
    from langgraph.types import Send

    opts = pipeline_options(state)
    questions = state.get("application_questions") or opts.application_questions
    if not questions:
        return []
    return [
        Send(
            "app_answer_worker",
            {
                "job_id": state["job_id"],
                "question": q,
                "resume_label": opts.resume_label,
            },
        )
        for q in questions
    ]
