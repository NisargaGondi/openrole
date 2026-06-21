"""Batch research + draft nodes (replaces Send workers)."""

from __future__ import annotations

from openrole.agents.batch_outreach import draft_contacts_batch
from openrole.agents.batch_research import research_contacts_batch
from openrole.agents.pipeline_progress import progress_entry, stamp
from openrole.api.activity_store import log as act_log
from openrole.graph.state import OpenRoleState
from openrole.schemas.pipeline import PipelineOptions


def batch_research_node(state: OpenRoleState) -> dict:
    job_id = state.get("job_id")
    contact_ids = list(state.get("contact_ids") or [])
    if not job_id or not contact_ids:
        return {
            "pipeline_stage": "research_skipped",
            **progress_entry("Research skipped — no contacts"),
        }

    progress: list[str] = [stamp(f"Batch research for {len(contact_ids)} contact(s)")]

    def _on_progress(msg: str) -> None:
        progress.append(msg)
        act_log(msg, icon="dot")

    act_log(progress[0], icon="dot")
    result = research_contacts_batch(
        job_id=job_id,
        contact_ids=contact_ids,
        on_progress=_on_progress,
    )
    progress.append(stamp(f"Research complete — {result.get('researched', 0)} brief(s)"))

    briefs = [
        {"contact_id": b["contact_id"], "status": b.get("status"), "brief": b.get("brief")}
        for b in result.get("research_briefs") or []
    ]
    return {
        "research_briefs": briefs,
        "pipeline_stage": "research_complete",
        "stages_completed": ["batch_research"],
        "progress_log": progress,
        "_live_progress": True,
    }


def batch_drafts_node(state: OpenRoleState) -> dict:
    job_id = state.get("job_id")
    contact_ids = list(state.get("contact_ids") or [])
    if not job_id or not contact_ids:
        return {
            "pipeline_stage": "drafts_skipped",
            **progress_entry("Drafts skipped — no contacts"),
        }

    progress: list[str] = [stamp(f"Batch outreach drafts for {len(contact_ids)} contact(s)")]

    def _on_progress(msg: str) -> None:
        progress.append(msg)
        act_log(msg, icon="dot")

    act_log(progress[0], icon="dot")
    result = draft_contacts_batch(
        job_id=job_id,
        contact_ids=contact_ids,
        on_progress=_on_progress,
    )
    progress.append(stamp(f"Drafts complete — {len(result.get('drafts') or [])} message(s) saved"))

    return {
        "outreach_drafts": result.get("drafts") or [],
        "draft_evaluations": result.get("draft_evaluations") or [],
        "warnings": result.get("profile_warnings") or [],
        "errors": result.get("errors") or [],
        "pipeline_stage": "outreach_drafted",
        "stages_completed": ["batch_drafts", "aggregate_outreach"],
        "progress_log": progress,
        "_live_progress": True,
    }


def route_batch_research(state: OpenRoleState) -> str:
    opts = PipelineOptions.from_state(state.get("pipeline_options"))
    if opts.run_research and state.get("contact_ids"):
        return "batch_research"
    return "skip_research"


def route_batch_drafts(state: OpenRoleState) -> str:
    opts = PipelineOptions.from_state(state.get("pipeline_options"))
    if opts.run_outreach and state.get("contact_ids"):
        return "batch_drafts"
    return "skip_drafts"
