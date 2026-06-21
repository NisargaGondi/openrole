"""Streamlit page paths and navigation helpers."""

from __future__ import annotations

import streamlit as st

PAGE_HOME = "pages/home.py"
PAGE_DASHBOARD = "pages/home.py"
PAGE_JOB_LIBRARY = "pages/add_jobs.py"
PAGE_SCOUT = "pages/scout.py"
PAGE_WORKBENCH = "pages/home.py"
PAGE_PIPELINE = "pages/home.py"
PAGE_SETTINGS = "pages/settings.py"


def go_to_home(*, job_id: str | None = None, step: str | None = None) -> None:
    if job_id:
        st.session_state["work_job_id"] = job_id
    if step:
        st.session_state["workbench_step"] = step
    st.switch_page(PAGE_HOME)


def go_to_job_library(*, job_id: str | None = None) -> None:
    if job_id:
        st.session_state["library_job_id"] = job_id
    st.switch_page(PAGE_JOB_LIBRARY)


def go_to_workbench(*, job_id: str | None = None, step: str | None = None) -> None:
    go_to_home(job_id=job_id, step=step)


def go_to_pipeline(*, job_id: str | None = None, tab: str = "pipeline") -> None:
    step_map = {"pipeline": "people", "outreach": "outreach", "apply": "apply", "role": "role"}
    go_to_home(job_id=job_id, step=step_map.get(tab, "people"))


def go_to_scout() -> None:
    st.switch_page(PAGE_SCOUT)


def go_to_dashboard() -> None:
    st.switch_page(PAGE_HOME)
