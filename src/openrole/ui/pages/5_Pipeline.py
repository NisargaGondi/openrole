"""Full LangGraph pipeline control — run, stream progress, resume after review gates."""

from __future__ import annotations

import streamlit as st
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from openrole.db.models import Job
from openrole.db.repository import get_pipeline_runs
from openrole.db.session import get_session_factory
from openrole.graph.pipeline_runner import (
    get_pipeline_state,
    resume_pipeline,
    run_pipeline_until_pause,
)
from openrole.schemas.pipeline import PipelineOptions

st.header("Pipeline")
st.caption(
    "LangGraph workflow: people discovery → parallel research → evaluator-optimized drafts "
    "→ review gates → resume / application prep."
)

factory = get_session_factory()

with factory() as session:
    jobs = list(
        session.scalars(
            select(Job)
            .options(joinedload(Job.company))
            .order_by(Job.created_at.desc())
            .limit(50)
        ).unique()
    )

if not jobs:
    st.info("Ingest a job on the **Jobs** tab first.")
    st.stop()

job_options = {f"{j.title} @ {(j.company.name if j.company else '—')}": j.id for j in jobs}
selected_label = st.selectbox("Job", options=list(job_options.keys()))
job_id = job_options[selected_label]

# Resume paused run
paused_tid = st.session_state.get("pipeline_thread_id")
if paused_tid:
    st.warning("Pipeline paused — waiting for your review.")
    paused = get_pipeline_state(paused_tid)
    for intr in paused.get("interrupts") or []:
        payload = intr.get("value") or {}
        st.subheader(f"Review: {payload.get('gate', 'gate')}")
        st.write(payload.get("message", ""))
        if payload.get("gate") == "outreach_review":
            st.info("Open **Outreach** to edit drafts, then continue or stop.")
        elif payload.get("gate") == "application_review":
            st.info("Open **Apply** to review resume score and questions.")
        if payload.get("evaluations"):
            with st.expander("Draft evaluations"):
                st.json(payload["evaluations"])
    col_a, col_b = st.columns(2)
    if col_a.button("Continue pipeline", type="primary"):
        result = resume_pipeline(paused_tid, approved=True)
        if result.interrupted:
            st.session_state["pipeline_thread_id"] = result.thread_id
            st.rerun()
        else:
            st.session_state.pop("pipeline_thread_id", None)
            st.success("Pipeline complete.")
            st.json({k: v for k, v in result.state.items() if k != "parsed_job"})
    if col_b.button("Stop here"):
        resume_pipeline(paused_tid, approved=False)
        st.session_state.pop("pipeline_thread_id", None)
        st.success("Stopped at review gate. Drafts are saved.")

st.divider()
st.subheader("Run pipeline")

c1, c2 = st.columns(2)
run_people = c1.checkbox("Find people", value=True)
run_research = c1.checkbox("Research contacts", value=True)
run_outreach = c1.checkbox("Draft outreach (evaluator loop)", value=True)
run_resume = c2.checkbox("Resume ATS analysis", value=True)
run_application = c2.checkbox("Application Q&A", value=False)

questions_text = st.text_area(
    "Application questions (one per line; required if Application Q&A enabled)",
    height=100,
    placeholder="Why do you want to work here?",
)
resume_label = st.text_input("Resume variant label (optional)", value="")

if st.button("Run full pipeline", type="primary"):
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
    try:
        with st.spinner("Running LangGraph pipeline…"):
            result = run_pipeline_until_pause(job_id=job_id, options=opts)
        if result.interrupted:
            st.session_state["pipeline_thread_id"] = result.thread_id
            st.warning("Pipeline paused for human review — use the section above to continue.")
            for intr in result.interrupts:
                val = getattr(intr, "value", intr)
                st.json(val)
        else:
            st.success("Pipeline finished.")
            st.json(
                {
                    "job_id": result.state.get("job_id"),
                    "contact_count": result.state.get("contact_count"),
                    "drafts": len(result.state.get("outreach_drafts") or []),
                    "resume_score": (result.state.get("resume_report") or {}).get("match_score"),
                    "errors": result.state.get("errors"),
                }
            )
    except Exception as exc:
        st.error(f"Pipeline failed: {exc}")

st.divider()
st.subheader("Run history")
with factory() as session:
    runs = get_pipeline_runs(session, job_id)
if not runs:
    st.write("No pipeline runs recorded yet.")
else:
    for run in runs[:8]:
        with st.expander(
            f"{run.get('completed_at', '?')[:19]} — {run.get('pipeline_stage')} "
            f"({len(run.get('stages_completed') or [])} stages)"
        ):
            st.json(run)
