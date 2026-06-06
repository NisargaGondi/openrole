"""Parallel outreach workers (research + evaluator-optimizer drafts)."""

from __future__ import annotations

from openrole.agents.draft_evaluator import draft_outreach_optimized
from openrole.agents.email_writer import EmailWriterError
from openrole.agents.person_research import PersonResearchError, research_contact_for_job
from openrole.graph.state import DraftWorkerState, ResearchWorkerState


def research_worker_node(state: ResearchWorkerState) -> dict:
    job_id = state.get("job_id")
    contact_id = state.get("contact_id")
    if not job_id or not contact_id:
        return {"errors": ["research_worker missing job_id or contact_id"]}
    try:
        result = research_contact_for_job(contact_id=contact_id, job_id=job_id)
        return {
            "research_briefs": [
                {"contact_id": contact_id, "status": result.get("status"), "brief": result.get("brief")}
            ],
            "stages_completed": [f"research:{contact_id}"],
        }
    except PersonResearchError as exc:
        return {"errors": [f"{contact_id}: {exc}"]}


def draft_worker_node(state: DraftWorkerState) -> dict:
    job_id = state.get("job_id")
    contact_id = state.get("contact_id")
    max_iters = int(state.get("max_draft_iterations") or 3)
    if not job_id or not contact_id:
        return {"errors": ["draft_worker missing job_id or contact_id"]}
    try:
        result = draft_outreach_optimized(
            contact_id=contact_id,
            job_id=job_id,
            max_iterations=max_iters,
        )
        evaluation = result.get("evaluation") or {}
        return {
            "outreach_drafts": result.get("drafts") or [],
            "draft_evaluations": [evaluation],
            "warnings": result.get("profile_warnings") or [],
            "stages_completed": [f"draft:{contact_id}"],
        }
    except EmailWriterError as exc:
        return {"errors": [f"{contact_id}: {exc}"]}


def aggregate_outreach_node(state: dict) -> dict:
    """Fan-in after Send workers complete."""
    drafts = state.get("outreach_drafts") or []
    evals = state.get("draft_evaluations") or []
    return {
        "pipeline_stage": "outreach_drafted",
        "stages_completed": ["aggregate_outreach"],
        "warnings": [
            f"Draft for {e.get('contact_id')}: grade={e.get('grade')} "
            f"(email {e.get('email_score')}, linkedin {e.get('linkedin_score')}) "
            f"after {e.get('attempts')} attempt(s)"
            for e in evals
            if e.get("grade") == "needs_work"
        ],
    }
