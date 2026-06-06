"""LangGraph orchestration — unified pipeline with HITL interrupts."""

from openrole.graph.main_graph import (
    discover_and_prepare_outreach_via_graph,
    discover_people_via_graph,
    get_pipeline_graph,
    run_pipeline,
)
from openrole.graph.pipeline_runner import (
    get_pipeline_state,
    resume_pipeline,
    run_job_pipeline_sync,
    run_pipeline_to_completion,
    run_pipeline_until_pause,
    stream_pipeline_updates,
)

__all__ = [
    "discover_and_prepare_outreach_via_graph",
    "discover_people_via_graph",
    "get_pipeline_graph",
    "get_pipeline_state",
    "resume_pipeline",
    "run_job_pipeline_sync",
    "run_pipeline",
    "run_pipeline_to_completion",
    "run_pipeline_until_pause",
    "stream_pipeline_updates",
]
