"""Background pipeline execution — survives SSE client disconnect."""

from __future__ import annotations

import json
import threading
from queue import Empty, Queue

from openrole.agents.pipeline_progress import merge_stream_logs, stamp
from openrole.api.activity_store import log as act_log
from openrole.api.pipeline_run_store import finish_run, is_cancel_requested, is_running, start_run
from openrole.graph.pipeline_runner import get_pipeline_state, stream_pipeline_until_done
from openrole.schemas.pipeline import PipelineOptions

_DONE = object()

_lock = threading.Lock()
_queues: dict[str, Queue] = {}
_threads: dict[str, threading.Thread] = {}


def emit_cancel_ack(job_id: str) -> bool:
    """Push immediate SSE event so the UI acknowledges cancel without waiting for a node."""
    from openrole.agents.pipeline_progress import stamp
    from openrole.api.activity_store import log as act_log

    with _lock:
        q = _queues.get(job_id)
    if not q:
        return False
    msg = stamp("Cancel requested — stopping after current step…")
    act_log(msg, level="warn", icon="alert")
    q.put({"type": "cancelling", "message": msg})
    return True


def ensure_pipeline_thread(
    job_id: str,
    opts: PipelineOptions,
    *,
    step: str,
    company: str | None,
) -> Queue:
    """Start pipeline in a background thread if not already running; return event queue."""
    with _lock:
        if job_id in _queues and _threads.get(job_id, threading.Thread()).is_alive():
            return _queues[job_id]

        q: Queue = Queue()
        _queues[job_id] = q
        start_run(job_id, step=step, company=company)
        act_log(f"Pipeline started ({job_id[:8]}…)", icon="dot")
        q.put(
            {
                "type": "start",
                "message": stamp("Pipeline started"),
            }
        )

        def worker() -> None:
            from openrole.api.pipeline_cancel import PipelineCancelled, pipeline_cancel_context
            from openrole.api.usage_tracker import record_from_log_line
            from openrole.llm.tracking import llm_usage_context

            thread_id = ""
            try:
                with (
                    pipeline_cancel_context(job_id),
                    llm_usage_context(job_id=job_id, company=company, pipeline_step=step),
                ):
                    for node_name, update in stream_pipeline_until_done(
                        job_id=job_id,
                        options=opts,
                        auto_approve=opts.auto_approve,
                    ):
                        if is_cancel_requested(job_id):
                            act_log(f"Pipeline cancelled ({job_id[:8]}…)", level="warn", icon="alert")
                            q.put({"type": "cancelled", "message": stamp("Pipeline cancelled by user")})
                            return
                        if node_name == "__meta__":
                            thread_id = update.get("thread_id") or thread_id
                            q.put({"type": "meta", "thread_id": thread_id})
                            continue
                        if node_name == "__log__":
                            line = str(update.get("message") or "")
                            if line:
                                act_log(line, icon="dot")
                                q.put({"type": "log", "message": line, "node": "review"})
                            continue
                        lines = merge_stream_logs(node_name, update)
                        live = bool(update.get("_live_progress"))
                        progress_set = set(update.get("progress_log") or [])
                        for line in lines:
                            if not (live and line in progress_set):
                                act_log(line, icon="dot")
                                record_from_log_line(
                                    line, job_id=job_id, company=company, pipeline_step=step
                                )
                            q.put({"type": "log", "message": line, "node": node_name})

                    snap = get_pipeline_state(thread_id) if thread_id else {"values": {}, "interrupts": []}
                    values = snap.get("values") or {}
                    interrupted = bool(snap.get("interrupts"))
                    msg = stamp(
                        f"Pipeline finished · {values.get('contact_count', 0)} contacts · "
                        f"{len(values.get('outreach_drafts') or [])} drafts"
                    )
                    act_log(msg, level="ok", icon="check")
                    q.put(
                        {
                            "type": "done",
                            "message": msg,
                            "contact_count": values.get("contact_count"),
                            "drafts": len(values.get("outreach_drafts") or []),
                            "interrupted": interrupted,
                            "errors": values.get("errors"),
                            "thread_id": thread_id,
                        }
                    )
            except PipelineCancelled:
                msg = stamp("Pipeline cancelled by user")
                act_log(msg, level="warn", icon="alert")
                q.put({"type": "cancelled", "message": msg})
            except Exception as exc:
                act_log(f"Pipeline error: {exc}", level="err", icon="alert")
                q.put({"type": "error", "message": str(exc)})
            finally:
                finish_run(job_id)
                q.put(_DONE)
                with _lock:
                    _threads.pop(job_id, None)
                    _queues.pop(job_id, None)

        t = threading.Thread(target=worker, name=f"pipeline-{job_id[:8]}", daemon=True)
        _threads[job_id] = t
        t.start()
        return q


def iter_sse_events(q: Queue, *, job_id: str) -> list[dict]:
    """Drain available events from queue (non-blocking batch)."""
    events: list[dict] = []
    while True:
        try:
            item = q.get_nowait()
        except Empty:
            break
        if item is _DONE:
            break
        events.append(item)
    return events


def wait_sse_event(q: Queue, *, timeout: float = 1.0) -> dict | None:
    try:
        item = q.get(timeout=timeout)
    except Empty:
        return None
    if item is _DONE:
        return None
    return item
