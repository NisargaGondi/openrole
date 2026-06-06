"""Unified LangGraph pipeline — workflow + Send workers + interrupt HITL."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from langgraph.graph import END, START, StateGraph

from openrole.graph.checkpoint import get_checkpointer
from openrole.graph.nodes.apply import (
    app_answer_worker_node,
    finalize_application_node,
    optimize_resume_node,
    prepare_application_node,
)
from openrole.graph.nodes.finalize import finalize_node
from openrole.graph.nodes.ingest import ingest_node
from openrole.graph.nodes.outreach import (
    aggregate_outreach_node,
    draft_worker_node,
    research_worker_node,
)
from openrole.graph.nodes.people import (
    discover_candidates_node,
    extract_context_node,
    persist_contacts_node,
    prepare_outreach_node,
    validate_contacts_node,
)
from openrole.graph.nodes.review import application_review_node, outreach_review_node
from openrole.graph.routing import (
    dispatch_app_answers,
    dispatch_drafts,
    dispatch_research,
    route_after_ingest,
    route_after_persist,
    route_entry,
    route_existing_job,
)
from openrole.graph.state import OpenRoleState
from openrole.schemas.pipeline import PipelineOptions


def _skip_research_node(state: OpenRoleState) -> dict:
    return {"pipeline_stage": "research_skipped", "stages_completed": ["skip_research"]}


def _aggregate_research_node(state: OpenRoleState) -> dict:
    return {"pipeline_stage": "research_complete", "stages_completed": ["aggregate_research"]}


def _skip_drafts_node(state: OpenRoleState) -> dict:
    return {"pipeline_stage": "drafts_skipped", "stages_completed": ["skip_drafts"]}


def _skip_app_node(state: OpenRoleState) -> dict:
    return {"pipeline_stage": "app_skipped", "stages_completed": ["skip_app_answers"]}


def _route_existing_wrapper(state: OpenRoleState) -> dict:
    return {"pipeline_stage": "routing"}


@lru_cache(maxsize=1)
def get_pipeline_graph():
    """Compile once with checkpointer for interrupts + resume."""
    graph = StateGraph(OpenRoleState)

    # Ingest & people
    graph.add_node("ingest", ingest_node)
    graph.add_node("route_existing", _route_existing_wrapper)
    graph.add_node("extract_context", extract_context_node)
    graph.add_node("discover_candidates", discover_candidates_node)
    graph.add_node("validate_contacts", validate_contacts_node)
    graph.add_node("persist_contacts", persist_contacts_node)

    # Outreach orchestrator + Send workers
    graph.add_node("prepare_outreach", prepare_outreach_node)
    graph.add_node("research_worker", research_worker_node)
    graph.add_node("skip_research", _skip_research_node)
    graph.add_node("aggregate_research", _aggregate_research_node)
    graph.add_node("draft_worker", draft_worker_node)
    graph.add_node("skip_drafts", _skip_drafts_node)
    graph.add_node("aggregate_outreach", aggregate_outreach_node)

    # HITL review gates
    graph.add_node("outreach_review", outreach_review_node)
    graph.add_node("application_review", application_review_node)

    # Apply stage
    graph.add_node("optimize_resume", optimize_resume_node)
    graph.add_node("prepare_application", prepare_application_node)
    graph.add_node("app_answer_worker", app_answer_worker_node)
    graph.add_node("skip_app_answers", _skip_app_node)
    graph.add_node("finalize_application", finalize_application_node)
    graph.add_node("finalize", finalize_node)

    # Entry routing
    graph.add_conditional_edges(START, route_entry, {"ingest": "ingest", "route_existing": "route_existing"})
    graph.add_conditional_edges(
        "ingest",
        route_after_ingest,
        {"route_existing": "route_existing", "finalize": "finalize"},
    )
    graph.add_conditional_edges(
        "route_existing",
        route_existing_job,
        {
            "extract_context": "extract_context",
            "prepare_outreach": "prepare_outreach",
            "optimize_resume": "optimize_resume",
            "prepare_application": "prepare_application",
            "finalize": "finalize",
        },
    )

    # People chain
    graph.add_edge("extract_context", "discover_candidates")
    graph.add_edge("discover_candidates", "validate_contacts")
    graph.add_conditional_edges(
        "validate_contacts",
        lambda s: "persist" if s.get("contacts") else "finalize",
        {"persist": "persist_contacts", "finalize": "finalize"},
    )
    graph.add_conditional_edges(
        "persist_contacts",
        route_after_persist,
        {
            "prepare_outreach": "prepare_outreach",
            "optimize_resume": "optimize_resume",
            "finalize": "finalize",
        },
    )

    # Research Send workers
    graph.add_conditional_edges(
        "prepare_outreach",
        dispatch_research,
        ["research_worker", "skip_research"],
    )
    graph.add_edge("research_worker", "aggregate_research")
    graph.add_edge("skip_research", "aggregate_research")
    graph.add_conditional_edges(
        "aggregate_research",
        dispatch_drafts,
        ["draft_worker", "skip_drafts"],
    )
    graph.add_edge("draft_worker", "aggregate_outreach")
    graph.add_edge("skip_drafts", "aggregate_outreach")
    graph.add_edge("aggregate_outreach", "outreach_review")

    graph.add_edge("optimize_resume", "application_review")

    graph.add_conditional_edges(
        "prepare_application",
        dispatch_app_answers,
        ["app_answer_worker", "skip_app_answers"],
    )
    graph.add_edge("app_answer_worker", "finalize_application")
    graph.add_edge("skip_app_answers", "finalize_application")
    graph.add_edge("finalize_application", "finalize")
    graph.add_edge("finalize", END)

    return graph.compile(checkpointer=get_checkpointer())


# --- Backward-compatible entrypoints ---


def build_graph(*, include_people_discovery: bool = False):
    """Legacy: ingest-only or ingest+people (no checkpointer)."""
    graph = StateGraph(OpenRoleState)
    graph.add_node("ingest", ingest_node)
    graph.add_edge(START, "ingest")
    if include_people_discovery:
        for name, fn in [
            ("extract_context", extract_context_node),
            ("discover_candidates", discover_candidates_node),
            ("validate_contacts", validate_contacts_node),
            ("persist_contacts", persist_contacts_node),
        ]:
            graph.add_node(name, fn)
        graph.add_conditional_edges(
            "ingest",
            lambda s: "extract_context"
            if s.get("job_id") and not s.get("errors")
            else "end",
            {"extract_context": "extract_context", "end": END},
        )
        graph.add_edge("extract_context", "discover_candidates")
        graph.add_edge("discover_candidates", "validate_contacts")
        graph.add_conditional_edges(
            "validate_contacts",
            lambda s: "persist" if s.get("contacts") else "end",
            {"persist": "persist_contacts", "end": END},
        )
        graph.add_edge("persist_contacts", END)
    else:
        graph.add_edge("ingest", END)
    return graph.compile()


def run_pipeline(
    *,
    job_url: str | None = None,
    job_text: str | None = None,
    run_people_discovery: bool = False,
) -> dict:
    from openrole.graph.pipeline_runner import run_pipeline_sync

    opts = PipelineOptions.people_only() if run_people_discovery else PipelineOptions(
        run_people=False,
        run_research=False,
        run_outreach=False,
        run_resume=False,
    )
    return run_pipeline_sync(
        job_url=job_url,
        job_text=job_text,
        options=opts,
        use_legacy_ingest_only=not run_people_discovery,
    )


def discover_people_via_graph(job_id: str) -> dict[str, Any]:
    from openrole.graph.pipeline_runner import run_job_pipeline_sync

    return run_job_pipeline_sync(job_id, options=PipelineOptions.people_only())


def discover_and_prepare_outreach_via_graph(job_id: str) -> dict[str, Any]:
    from openrole.graph.pipeline_runner import run_job_pipeline_sync

    return run_job_pipeline_sync(job_id, options=PipelineOptions.outreach_prep())
