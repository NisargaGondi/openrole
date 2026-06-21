"""Pipeline controls for a selected job."""

from __future__ import annotations

import html

import streamlit as st

from openrole.agents.pipeline_progress import merge_stream_logs, stamp
from openrole.db.repository import get_pipeline_runs
from openrole.db.session import get_session_factory
from openrole.graph.pipeline_runner import (
    get_pipeline_state,
    resume_pipeline,
    stream_pipeline_updates,
)
from openrole.schemas.pipeline import PipelineOptions
from openrole.ui.activity import append_log_line, log_activity
from openrole.ui.components.pipeline_log import render_pipeline_log


def _render_log_html(lines: list[str]) -> str:
    body = html.escape("\n".join(lines[-50:]))
    return f'<pre class="or-pipe-log">{body}</pre>'


def render_pipeline_section(job_id: str, *, key_prefix: str = "wf") -> None:
    st.subheader("People pipeline")
    st.caption("Find people → research → outreach drafts → resume prep. Run from this step or jump ahead when ready.")

    paused_tid = st.session_state.get("pipeline_thread_id")
    if paused_tid:
        st.warning("Pipeline paused — waiting for your review.")
        paused = get_pipeline_state(paused_tid)
        for intr in paused.get("interrupts") or []:
            payload = intr.get("value") or {}
            st.write(payload.get("message", ""))
        col_a, col_b = st.columns(2)
        if col_a.button("Continue pipeline", type="primary", key=f"{key_prefix}_pipe_cont"):
            _resume_with_log(paused_tid, approved=True, key_prefix=key_prefix)
        if col_b.button("Stop at gate", key=f"{key_prefix}_pipe_stop"):
            resume_pipeline(paused_tid, approved=False)
            st.session_state.pop("pipeline_thread_id", None)
            st.success("Stopped — drafts saved.")
            st.rerun()

    c1, c2 = st.columns(2)
    run_people = c1.checkbox("Find people", value=True, key=f"{key_prefix}_pp")
    run_research = c1.checkbox("Research contacts", value=True, key=f"{key_prefix}_pr")
    run_outreach = c1.checkbox("Draft outreach", value=True, key=f"{key_prefix}_po")
    run_resume = c2.checkbox("Resume ATS analysis", value=False, key=f"{key_prefix}_prs")
    run_application = c2.checkbox("Application Q&A", value=False, key=f"{key_prefix}_pa")
    questions_text = st.text_area("Application questions (one per line)", height=80, key=f"{key_prefix}_pq")
    resume_label = st.text_input("Resume variant (optional)", key=f"{key_prefix}_pl")

    factory = get_session_factory()
    with factory() as session:
        runs = get_pipeline_runs(session, job_id)
    if runs:
        with st.expander("Run history"):
            for run in runs[:5]:
                st.caption(
                    f"{(run.get('completed_at') or '')[:19]} — {run.get('pipeline_stage')}"
                )

    if st.button("Run pipeline", type="primary", key=f"{key_prefix}_run_pipe"):
        questions = [ln.strip() for ln in questions_text.splitlines() if ln.strip()]
        opts = PipelineOptions(
            run_people=run_people,
            run_research=run_research,
            run_outreach=run_outreach,
            run_resume=run_resume,
            run_application=run_application and bool(questions),
            application_questions=questions,
            resume_label=resume_label.strip() or None,
        )
        logs: list[str] = [stamp("Pipeline started")]
        log_activity("Pipeline started", level="info")
        log_area = st.empty()
        log_area.markdown(_render_log_html(logs), unsafe_allow_html=True)
        try:
            interrupted = False
            thread_id = ""
            final_state: dict = {}
            for node_name, update in stream_pipeline_updates(job_id=job_id, options=opts):
                if node_name == "__meta__":
                    thread_id = update.get("thread_id") or thread_id
                    continue
                new_lines = merge_stream_logs(node_name, update)
                logs.extend(new_lines)
                for ln in new_lines:
                    append_log_line(ln)
                log_area.markdown(_render_log_html(logs), unsafe_allow_html=True)
                final_state.update(update)

            if thread_id:
                snap = get_pipeline_state(thread_id)
                if snap.get("interrupts"):
                    interrupted = True

            st.session_state["pipeline_run_log"] = logs
            if interrupted and thread_id:
                st.session_state["pipeline_thread_id"] = thread_id
                logs.append(stamp("Paused for review — continue above"))
                st.warning("Paused for review — continue above or open the **Outreach** step.")
            else:
                count = final_state.get("contact_count", 0)
                logs.append(stamp("Pipeline finished"))
                log_activity("Pipeline finished", level="ok")
                if opts.run_people and count:
                    st.session_state["workbench_step"] = "research" if opts.run_research else "people"
                    st.success(
                        f"Pipeline finished — {count} contact(s) saved. "
                        "Continue in the **Research** or **Outreach** step."
                    )
                else:
                    st.success("Pipeline finished.")
            st.rerun()
        except Exception as exc:
            logs.append(stamp(f"Error: {exc}"))
            st.session_state["pipeline_run_log"] = logs
            st.error(str(exc))

    st.divider()
    if "pipeline_run_log" not in st.session_state:
        st.session_state["pipeline_run_log"] = []
    render_pipeline_log(st.session_state["pipeline_run_log"])


def _resume_with_log(thread_id: str, *, approved: bool, key_prefix: str = "wf") -> None:
    logs = list(st.session_state.get("pipeline_run_log") or [])
    logs.append(stamp("Resuming pipeline…"))
    try:
        result = resume_pipeline(thread_id, approved=approved)
        if result.state:
            logs.append(stamp(f"Resumed → stage {result.state.get('pipeline_stage', '?')}"))
        if result.interrupted:
            st.session_state["pipeline_thread_id"] = result.thread_id
            logs.append(stamp("Paused again — waiting for review"))
        else:
            st.session_state.pop("pipeline_thread_id", None)
            logs.append(stamp("Pipeline complete"))
            st.success("Pipeline complete.")
        st.session_state["pipeline_run_log"] = logs
        st.rerun()
    except Exception as exc:
        logs.append(stamp(f"Error: {exc}"))
        st.session_state["pipeline_run_log"] = logs
        st.error(str(exc))
