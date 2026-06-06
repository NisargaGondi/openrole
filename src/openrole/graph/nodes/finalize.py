"""Pipeline finalization and run metadata persistence."""

from __future__ import annotations

from datetime import UTC, datetime

from openrole.db.repository import save_pipeline_run
from openrole.db.session import session_scope
from openrole.graph.state import OpenRoleState


def finalize_node(state: OpenRoleState) -> dict:
    job_id = state.get("job_id")
    run_meta = {
        "run_id": state.get("run_id"),
        "thread_id": state.get("thread_id"),
        "completed_at": datetime.now(UTC).isoformat(),
        "pipeline_stage": state.get("pipeline_stage"),
        "stages_completed": state.get("stages_completed") or [],
        "contact_count": state.get("contact_count"),
        "draft_count": len(state.get("outreach_drafts") or []),
        "resume_score": (state.get("resume_report") or {}).get("match_score"),
        "errors": state.get("errors") or [],
        "warnings": (state.get("warnings") or [])[-10:],
        "interrupted": False,
    }
    if job_id:
        with session_scope() as session:
            save_pipeline_run(session, job_id=job_id, run_meta=run_meta)
            session.commit()
    return {
        "pipeline_stage": "complete",
        "stages_completed": ["finalize"],
    }
