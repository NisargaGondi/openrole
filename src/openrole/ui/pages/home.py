"""Mission Control — Signal network home."""

from __future__ import annotations

import json

import streamlit as st
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from openrole.db.models import Job
from openrole.db.repository import list_jobs_for_tracker
from openrole.db.session import get_session_factory
from openrole.ui.components.activity_log import render_activity_log_panel
from openrole.ui.components.integrations_bar import render_integrations_bar
from openrole.ui.components.job_brief_card import render_job_brief_card
from openrole.ui.components.job_detail import job_option_label, render_job_detail
from openrole.ui.components.page_header import render_page_header
from openrole.ui.components.pipeline_rail import render_pipeline_rail
from openrole.ui.components.signal_network_graph import render_signal_network_graph
from openrole.ui.navigation import go_to_scout
from openrole.ui.sections.apply_section import render_apply_section
from openrole.ui.sections.ingest_section import render_ingest_section
from openrole.ui.sections.outreach_section import render_outreach_section
from openrole.ui.sections.pipeline_section import render_pipeline_section
from openrole.ui.sections.research_section import render_research_section

render_page_header("home")
render_integrations_bar(compact=True)

factory = get_session_factory()
preselect = st.session_state.get("work_job_id")

with factory() as session:
    jobs = list_jobs_for_tracker(session, status="all", limit=300)
    if preselect and not any(j.id == preselect for j in jobs):
        extra = session.scalar(
            select(Job).options(joinedload(Job.company)).where(Job.id == preselect).limit(1)
        )
        if extra:
            jobs = [extra, *jobs]

if not jobs:
    st.markdown('<div class="or-sig-panel">', unsafe_allow_html=True)
    st.markdown("#### Connect your first role")
    st.caption("Ingest a URL or run Scout — your network graph will light up here.")
    render_ingest_section()
    st.markdown("</div>", unsafe_allow_html=True)
    if st.button("Run Scout", type="primary"):
        go_to_scout()
    render_activity_log_panel()
    st.stop()

labels = [job_option_label(j) for j in jobs]
id_by_label = {job_option_label(j): j.id for j in jobs}
default_idx = next((i for i, j in enumerate(jobs) if j.id == preselect), 0)

pick_l, pick_r = st.columns([5, 1])
with pick_l:
    selected_label = st.selectbox(
        "Active role",
        options=labels,
        index=default_idx,
        key="mc_job_pick",
        label_visibility="collapsed",
    )
job_id = id_by_label[selected_label]
st.session_state["work_job_id"] = job_id
job = next(j for j in jobs if j.id == job_id)

with pick_r:
    if job.source_url:
        st.link_button("Posting ↗", job.source_url, use_container_width=True)

active_step = st.session_state.get("workbench_step", "role")

rail_col, main_col, log_col = st.columns([0.95, 2.5, 1.1])

with rail_col:
    active_step = render_pipeline_rail(job=job, active_step=active_step)

with log_col:
    render_activity_log_panel()

with main_col:
    render_signal_network_graph(job=job, active_step=active_step)
    render_job_brief_card(job)
    st.markdown('<div class="or-sig-panel">', unsafe_allow_html=True)
    if active_step == "role":
        render_job_detail(job, show_actions=False)
        if st.button("Signal → Find people", type="primary", key="mc_to_people"):
            st.session_state["workbench_step"] = "people"
            st.rerun()
    elif active_step == "people":
        render_pipeline_section(job_id, key_prefix="mc")
    elif active_step == "research":
        render_research_section(job_id)
    elif active_step == "outreach":
        render_outreach_section(job_id)
    elif active_step == "apply":
        render_apply_section(job_id)
    st.markdown("</div>", unsafe_allow_html=True)

with st.expander("Quick ingest another role"):
    render_ingest_section(key_prefix="mc_ing")
