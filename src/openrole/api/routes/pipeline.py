"""Pipeline execution with SSE streaming."""

from __future__ import annotations

import json
from collections.abc import Iterator

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from openrole.api.pipeline_run_store import get_active_runs, is_running, request_cancel
from openrole.api.pipeline_worker import ensure_pipeline_thread, wait_sse_event
from openrole.db.repository import get_job_with_company
from openrole.db.session import session_scope
from openrole.schemas.pipeline import PipelineOptions

router = APIRouter(tags=["pipeline"])


class PipelineBody(BaseModel):
    run_people: bool = True
    run_research: bool = True
    run_outreach: bool = True
    run_resume: bool = False
    run_application: bool = False
    application_questions: list[str] = Field(default_factory=list)
    resume_label: str | None = None
    resume_labels: list[str] | None = None
    auto_approve: bool = False


def _opts_from_query(
    *,
    run_people: bool,
    run_research: bool,
    run_outreach: bool,
    run_resume: bool,
    resume_label: str | None,
    resume_labels: list[str] | None,
    auto_approve: bool = False,
) -> PipelineOptions:
    return PipelineOptions(
        run_people=run_people,
        run_research=run_research,
        run_outreach=run_outreach,
        run_resume=run_resume,
        run_application=False,
        resume_label=resume_label,
        resume_labels=resume_labels,
        auto_approve=auto_approve,
    )


def _step_from_opts(opts: PipelineOptions) -> str:
    enabled = [opts.run_people, opts.run_research, opts.run_outreach, opts.run_resume]
    if sum(enabled) > 1 or opts.auto_approve:
        return "pipeline"
    if opts.run_people:
        return "people"
    if opts.run_research:
        return "research"
    if opts.run_outreach:
        return "outreach"
    if opts.run_resume:
        return "apply"
    return "pipeline"


def _sse_stream(job_id: str, opts: PipelineOptions) -> Iterator[str]:
    step = _step_from_opts(opts)
    company: str | None = None
    with session_scope() as session:
        job = get_job_with_company(session, job_id)
        if job and job.company:
            company = job.company.name

    q = ensure_pipeline_thread(job_id, opts, step=step, company=company)

    while True:
        ev = wait_sse_event(q, timeout=1.0)
        if ev is None:
            if not is_running(job_id):
                break
            continue
        yield f"data: {json.dumps(ev)}\n\n"
        if ev.get("type") in ("done", "error", "cancelled"):
            break


@router.get("/pipeline/status")
def pipeline_status():
    return {"runs": get_active_runs()}


@router.post("/jobs/{job_id}/pipeline/cancel")
def cancel_pipeline(job_id: str):
    from openrole.api.pipeline_worker import emit_cancel_ack

    if not request_cancel(job_id):
        raise HTTPException(404, "No active pipeline run for this job")
    emit_cancel_ack(job_id)
    return {"cancelled": True, "job_id": job_id, "acknowledged": True}


@router.get("/jobs/{job_id}/pipeline/stream")
def stream_pipeline(
    job_id: str,
    run_people: bool = Query(False),
    run_research: bool = Query(False),
    run_outreach: bool = Query(False),
    run_resume: bool = Query(False),
    resume_label: str | None = Query(None),
    resume_labels: str | None = Query(None, description="Comma-separated resume labels, or __all__"),
    auto_approve: bool = Query(False),
):
    """SSE stream — avoids HTTP timeout for long LangGraph runs."""
    if not any([run_people, run_research, run_outreach, run_resume]):
        raise HTTPException(400, "Enable at least one pipeline stage")
    labels = [s.strip() for s in resume_labels.split(",") if s.strip()] if resume_labels else None
    opts = _opts_from_query(
        run_people=run_people,
        run_research=run_research,
        run_outreach=run_outreach,
        run_resume=run_resume,
        resume_label=resume_label,
        resume_labels=labels,
        auto_approve=auto_approve,
    )
    return StreamingResponse(
        _sse_stream(job_id, opts),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/jobs/{job_id}/pipeline")
def run_pipeline(job_id: str, body: PipelineBody):
    """Redirect clients to SSE stream — sync POST kept for compatibility."""
    from openrole.api.activity_store import log as act_log
    from openrole.graph.pipeline_runner import run_pipeline_until_pause

    act_log("Pipeline started", icon="dot")
    opts = PipelineOptions(
        run_people=body.run_people,
        run_research=body.run_research,
        run_outreach=body.run_outreach,
        run_resume=body.run_resume,
        run_application=body.run_application and bool(body.application_questions),
        application_questions=body.application_questions,
        resume_label=body.resume_label,
        resume_labels=body.resume_labels,
        auto_approve=body.auto_approve,
    )
    try:
        result = run_pipeline_until_pause(job_id=job_id, options=opts)
    except Exception as exc:
        act_log(f"Pipeline error: {exc}", level="err", icon="alert")
        raise HTTPException(500, str(exc)) from exc

    state = result.state
    if result.interrupted:
        act_log("Pipeline paused for review", level="warn", icon="dot")
    else:
        act_log(
            f"Pipeline finished · {state.get('contact_count', 0)} contacts",
            level="ok",
            icon="check",
        )
    return {
        "interrupted": result.interrupted,
        "thread_id": result.thread_id,
        "contact_count": state.get("contact_count"),
        "drafts": len(state.get("outreach_drafts") or []),
        "errors": state.get("errors"),
    }
