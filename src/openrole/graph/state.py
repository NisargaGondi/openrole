"""Shared LangGraph state with reducers for parallel workers."""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


def _merge_stage(left: str | None, right: str | None) -> str | None:
    return right if right is not None else left


class OpenRoleState(TypedDict, total=False):
    """State passed between LangGraph nodes and subgraphs."""

    # Run identity
    thread_id: str
    run_id: str
    pipeline_options: dict[str, Any]

    # Ingest inputs
    job_url: str
    job_description_text: str
    job_id: str
    parsed_job: dict[str, Any]
    company: dict[str, Any]

    # People discovery
    search_context: dict[str, Any]
    location_target: dict[str, Any]
    company_domain: str
    contact_candidates: list[dict[str, Any]]
    contacts: list[dict[str, Any]]
    contact_count: int
    validation_result: dict[str, Any]

    # Outreach orchestration (Send workers)
    contact_ids: list[str]
    application_questions: list[str]

    research_briefs: Annotated[list[dict[str, Any]], operator.add]
    outreach_drafts: Annotated[list[dict[str, Any]], operator.add]
    draft_evaluations: Annotated[list[dict[str, Any]], operator.add]
    application_answers: Annotated[list[dict[str, Any]], operator.add]

    # Apply outputs
    resume_report: dict[str, Any]
    application_draft: dict[str, Any]

    # Progress
    pipeline_stage: Annotated[str | None, _merge_stage]
    stages_completed: Annotated[list[str], operator.add]

    warnings: Annotated[list[str], operator.add]
    errors: Annotated[list[str], operator.add]


class ResearchWorkerState(TypedDict, total=False):
    job_id: str
    contact_id: str
    research_briefs: Annotated[list[dict[str, Any]], operator.add]
    errors: Annotated[list[str], operator.add]
    warnings: Annotated[list[str], operator.add]


class DraftWorkerState(TypedDict, total=False):
    job_id: str
    contact_id: str
    max_draft_iterations: int
    outreach_drafts: Annotated[list[dict[str, Any]], operator.add]
    draft_evaluations: Annotated[list[dict[str, Any]], operator.add]
    errors: Annotated[list[str], operator.add]
    warnings: Annotated[list[str], operator.add]


class AppAnswerWorkerState(TypedDict, total=False):
    job_id: str
    question: str
    resume_label: str | None
    application_answers: Annotated[list[dict[str, Any]], operator.add]
    errors: Annotated[list[str], operator.add]
