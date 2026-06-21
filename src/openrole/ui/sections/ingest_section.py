"""Ingest a job URL or pasted description."""

from __future__ import annotations

import streamlit as st

from openrole.agents.job_ingestion import JobIngestionError, ingest_job
from openrole.graph.main_graph import run_pipeline
from openrole.tools import jobspy_client
from openrole.ui.activity import log_activity
from openrole.ui.navigation import go_to_home


def render_ingest_section(*, key_prefix: str = "ing") -> None:
    if not jobspy_client.is_available():
        st.caption("JobSpy optional — paste text for LinkedIn/Indeed if needed.")
    job_url = st.text_input(
        "Job URL",
        placeholder="Greenhouse, Lever, Handshake, Indeed, company careers page…",
        key=f"{key_prefix}_url",
    )
    job_text = st.text_area(
        "Or paste description",
        height=100,
        key=f"{key_prefix}_text",
    )
    if st.button("Ingest & open in Mission Control", type="primary", key=f"{key_prefix}_save"):
        try:
            log_activity("Ingest started…")
            with st.spinner("Fetching and parsing…"):
                result = ingest_job(
                    job_url=job_url.strip() or None,
                    job_text=job_text.strip() or None,
                )
            jid = result["job_id"]
            log_activity(f"Ingest saved job {jid[:8]}…", level="ok")
            st.session_state["library_job_id"] = jid
            st.session_state["work_job_id"] = jid
            st.session_state["workbench_step"] = "role"
            st.success("Saved — opening in Home.")
            go_to_home(job_id=jid, step="role")
        except JobIngestionError as exc:
            log_activity(str(exc), level="err")
            st.error(str(exc))
