"""Run, stream, and resume the OpenRole LangGraph pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterator
from uuid import uuid4

from langgraph.types import Command

from openrole.graph.checkpoint import make_thread_id, run_config
from openrole.graph.main_graph import build_graph, get_pipeline_graph
from openrole.graph.state import OpenRoleState
from openrole.schemas.pipeline import PipelineOptions


@dataclass
class PipelineRunResult:
    state: dict[str, Any]
    interrupted: bool = False
    interrupts: list[Any] = field(default_factory=list)
    thread_id: str = ""
    run_id: str = ""


def _initial_state(
    *,
    job_id: str | None = None,
    job_url: str | None = None,
    job_text: str | None = None,
    options: PipelineOptions | None = None,
    thread_id: str | None = None,
    run_id: str | None = None,
) -> OpenRoleState:
    rid = run_id or str(uuid4())[:8]
    tid = thread_id or (make_thread_id(job_id=job_id, run_id=rid) if job_id else f"new:{rid}")
    state: OpenRoleState = {
        "errors": [],
        "warnings": [],
        "research_briefs": [],
        "outreach_drafts": [],
        "draft_evaluations": [],
        "application_answers": [],
        "stages_completed": [],
        "pipeline_options": (options or PipelineOptions()).to_state_dict(),
        "thread_id": tid,
        "run_id": rid,
    }
    if job_id:
        state["job_id"] = job_id
    if job_url:
        state["job_url"] = job_url
    if job_text:
        state["job_description_text"] = job_text
    return state


def run_job_pipeline_sync(
    job_id: str,
    *,
    options: PipelineOptions | None = None,
    thread_id: str | None = None,
) -> dict[str, Any]:
    """Run full pipeline for an existing job; returns final state (may include __interrupt__)."""
    result = run_pipeline_until_pause(
        job_id=job_id,
        options=options,
        thread_id=thread_id,
    )
    return _merge_interrupt_result(result)


def run_pipeline_sync(
    *,
    job_url: str | None = None,
    job_text: str | None = None,
    options: PipelineOptions | None = None,
    use_legacy_ingest_only: bool = False,
) -> dict[str, Any]:
    if use_legacy_ingest_only:
        app = build_graph(include_people_discovery=False)
        initial: OpenRoleState = {"errors": [], "warnings": []}
        if job_url:
            initial["job_url"] = job_url
        if job_text:
            initial["job_description_text"] = job_text
        return app.invoke(initial)

    result = run_pipeline_until_pause(
        job_url=job_url,
        job_text=job_text,
        options=options,
    )
    return _merge_interrupt_result(result)


def run_pipeline_until_pause(
    *,
    job_id: str | None = None,
    job_url: str | None = None,
    job_text: str | None = None,
    options: PipelineOptions | None = None,
    thread_id: str | None = None,
) -> PipelineRunResult:
    app = get_pipeline_graph()
    initial = _initial_state(
        job_id=job_id,
        job_url=job_url,
        job_text=job_text,
        options=options,
        thread_id=thread_id,
    )
    config = run_config(thread_id=initial["thread_id"])
    raw = app.invoke(initial, config=config)
    interrupted = bool(raw.get("__interrupt__"))
    interrupts = list(raw.get("__interrupt__") or [])
    if not interrupts:
        snap = app.get_state(config)
        interrupts = list(snap.interrupts or ())
    return PipelineRunResult(
        state=dict(raw),
        interrupted=interrupted,
        interrupts=interrupts,
        thread_id=initial["thread_id"],
        run_id=initial["run_id"],
    )


def resume_pipeline(
    thread_id: str,
    *,
    approved: bool = True,
    resume_value: dict[str, Any] | None = None,
) -> PipelineRunResult:
    """Resume after interrupt; pass approved=False to stop at gate."""
    app = get_pipeline_graph()
    config = run_config(thread_id=thread_id)
    payload = resume_value if resume_value is not None else {"approved": approved}
    raw = app.invoke(Command(resume=payload), config=config)
    interrupted = bool(raw.get("__interrupt__"))
    interrupts = list(raw.get("__interrupt__") or [])
    if not interrupts:
        snap = app.get_state(config)
        interrupts = list(snap.interrupts or ())
    return PipelineRunResult(
        state=dict(raw),
        interrupted=interrupted,
        interrupts=interrupts,
        thread_id=thread_id,
        run_id=(raw.get("run_id") or ""),
    )


def run_pipeline_to_completion(
    *,
    job_id: str | None = None,
    job_url: str | None = None,
    job_text: str | None = None,
    options: PipelineOptions | None = None,
    auto_approve: bool = False,
) -> dict[str, Any]:
    """Run until complete, optionally auto-approving review gates (for tests)."""
    result = run_pipeline_until_pause(
        job_id=job_id,
        job_url=job_url,
        job_text=job_text,
        options=options,
    )
    while result.interrupted and auto_approve:
        result = resume_pipeline(result.thread_id, approved=True)
    return _merge_interrupt_result(result)


def stream_and_run(
    *,
    job_id: str | None = None,
    job_url: str | None = None,
    job_text: str | None = None,
    options: PipelineOptions | None = None,
    thread_id: str | None = None,
) -> PipelineRunResult:
    """Stream updates while running; return final or interrupted state."""
    app = get_pipeline_graph()
    initial = _initial_state(
        job_id=job_id,
        job_url=job_url,
        job_text=job_text,
        options=options,
        thread_id=thread_id,
    )
    config = run_config(thread_id=initial["thread_id"])
    list(app.stream(initial, config=config, stream_mode="updates", subgraphs=True))
    snap = app.get_state(config)
    values = dict(snap.values or {})
    interrupts = list(snap.interrupts or ())
    return PipelineRunResult(
        state=values,
        interrupted=bool(interrupts),
        interrupts=interrupts,
        thread_id=initial["thread_id"],
        run_id=initial.get("run_id") or "",
    )


def stream_pipeline_updates(
    *,
    job_id: str | None = None,
    job_url: str | None = None,
    job_text: str | None = None,
    options: PipelineOptions | None = None,
    thread_id: str | None = None,
) -> Iterator[tuple[str, dict[str, Any]]]:
    """Stream per-node updates (stream_mode=updates) for Pipeline UI progress."""
    app = get_pipeline_graph()
    initial = _initial_state(
        job_id=job_id,
        job_url=job_url,
        job_text=job_text,
        options=options,
        thread_id=thread_id,
    )
    config = run_config(thread_id=initial["thread_id"])
    for chunk in app.stream(initial, config=config, stream_mode="updates", subgraphs=True):
        if isinstance(chunk, tuple) and len(chunk) == 2:
            _namespace, data = chunk
            if isinstance(data, dict):
                for node_name, update in data.items():
                    yield node_name, update if isinstance(update, dict) else {"_raw": update}
        elif isinstance(chunk, dict):
            for node_name, update in chunk.items():
                yield node_name, update if isinstance(update, dict) else {"_raw": update}


def get_pipeline_state(thread_id: str) -> dict[str, Any]:
    app = get_pipeline_graph()
    snap = app.get_state(run_config(thread_id=thread_id))
    return {
        "values": dict(snap.values or {}),
        "next": list(snap.next or ()),
        "interrupts": [
            {"id": i.id, "value": i.value} for i in (snap.interrupts or ())
        ],
    }


def _merge_interrupt_result(result: PipelineRunResult) -> dict[str, Any]:
    state = dict(result.state)
    if result.interrupted:
        state["__interrupt__"] = result.interrupts
        state["interrupted"] = True
        state["thread_id"] = result.thread_id
    return state
