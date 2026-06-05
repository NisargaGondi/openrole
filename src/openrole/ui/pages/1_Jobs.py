"""Jobs list and ingestion."""

import streamlit as st
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from openrole.agents.job_ingestion import JobIngestionError, ingest_job
from openrole.db.models import Job
from openrole.db.session import get_session_factory
from openrole.graph.main_graph import run_pipeline

st.header("Jobs")

tab_ingest, tab_list = st.tabs(["Ingest", "Saved jobs"])

with tab_ingest:
    st.subheader("Add a job")
    if not jobspy_client.is_available():
        st.warning(
            "JobSpy is not installed — LinkedIn/Indeed URLs need pasted text, or run "
            "`bash scripts/install_jobspy.sh`."
        )
    job_url = st.text_input("Job URL", placeholder="Greenhouse, Lever, Ashby, LinkedIn, Indeed…")
    job_text = st.text_area(
        "Pasted description (fallback for LinkedIn; optional for Workday errors)",
        height=160,
    )
    col1, col2 = st.columns(2)
    with col1:
        run_direct = st.button("Ingest & save", type="primary")
    with col2:
        run_graph = st.button("Run via LangGraph")

    if run_direct:
        try:
            with st.spinner("Fetching and parsing…"):
                result = ingest_job(
                    job_url=job_url.strip() or None,
                    job_text=job_text.strip() or None,
                )
            st.success(f"Saved job `{result['job_id']}`")
            if result.get("warnings"):
                for w in result["warnings"]:
                    st.warning(w)
            st.json(result["parsed_job"])
        except JobIngestionError as exc:
            st.error(str(exc))
        except Exception as exc:
            st.error(f"Unexpected error: {exc}")

    if run_graph:
        try:
            with st.spinner("Running pipeline…"):
                state = run_pipeline(
                    job_url=job_url.strip() or None,
                    job_text=job_text.strip() or None,
                )
            if state.get("errors"):
                st.error("\n".join(state["errors"]))
            else:
                st.success(f"Saved job `{state.get('job_id')}`")
                for w in state.get("warnings") or []:
                    st.warning(w)
                st.json(state.get("parsed_job"))
        except Exception as exc:
            st.error(str(exc))

with tab_list:
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
        st.write("No jobs yet. Use the Ingest tab to add one.")
    else:
        for job in jobs:
            company_name = job.company.name if job.company else "—"
            label = f"{job.title} @ {company_name} ({job.status.value})"
            with st.expander(label):
                st.write(f"**Platform:** {job.source_platform or '—'}")
                st.write(f"**Department:** {job.department or '—'}")
                st.write(f"**Locations:** {', '.join(job.locations or []) or '—'}")
                if job.source_url:
                    st.link_button("Posting", job.source_url)
                if job.description:
                    st.text(job.description[:2000] + ("…" if len(job.description) > 2000 else ""))
