"""Browsable table of all ingested and scouted jobs."""

from __future__ import annotations

import streamlit as st

from openrole.db.models import JOB_STATUS_LABELS, Job
from openrole.db.repository import delete_job, list_jobs_for_tracker
from openrole.db.session import session_scope
from openrole.ui.components.job_detail import render_job_detail
from openrole.ui.navigation import go_to_home


def _handle_delete(job_id: str) -> None:
    with session_scope() as session:
        deleted = delete_job(session, job_id)
    if not deleted:
        st.error("Could not delete — job not found.")
        return
    if st.session_state.get("library_job_id") == job_id:
        st.session_state.pop("library_job_id", None)
    if st.session_state.get("work_job_id") == job_id:
        st.session_state.pop("work_job_id", None)
    st.toast("Role removed from library")
    st.rerun()


def _job_search_blob(job: Job) -> str:
    scout = (job.raw_payload or {}).get("scout") or {}
    parts = [
        job.id or "",
        job.title or "",
        job.company.name if job.company else "",
        job.company.domain if job.company and job.company.domain else "",
        job.source_platform or "",
        scout.get("source") or "",
        scout.get("search_term") or "",
        job.status.value if job.status else "",
    ]
    return " ".join(str(p).lower() for p in parts if p)


def render_job_library(*, factory, preselect_id: str | None = None) -> None:
    source_filter = st.radio(
        "Show",
        options=["all", "scout", "manual"],
        format_func=lambda v: {
            "all": "All saved roles",
            "scout": "From job scout only",
            "manual": "Added manually only",
        }[v],
        horizontal=True,
        label_visibility="collapsed",
    )

    with factory() as session:
        jobs = list_jobs_for_tracker(session, status="all", limit=300)

    if source_filter == "scout":
        jobs = [j for j in jobs if (j.raw_payload or {}).get("scout")]
    elif source_filter == "manual":
        jobs = [j for j in jobs if not (j.raw_payload or {}).get("scout")]

    search = st.text_input(
        "Search roles",
        placeholder="Title, company, domain, job id, source…",
        key="library_search",
    ).strip().lower()

    if search:
        jobs = [j for j in jobs if search in _job_search_blob(j)]

    st.caption(f"**{len(jobs)}** roles" + (f" matching “{search}”" if search else " in your library"))

    if not jobs:
        st.info("No jobs match — clear search or add a URL / run **Job scout**.")
        return

    expand_id = preselect_id or st.session_state.get("library_job_id")

    for job in jobs:
        scout = (job.raw_payload or {}).get("scout") or {}
        company = job.company.name if job.company else "—"
        score = scout.get("relevance_score")
        title = job.title if len(job.title) <= 72 else job.title[:69] + "…"
        status = JOB_STATUS_LABELS.get(job.status.value, job.status.value)
        source = job.source_platform or ("scout" if scout else "—")
        added = job.created_at.isoformat()[:10] if job.created_at else "—"
        score_txt = str(score) if score is not None else "—"

        header = f"**{title}** · {company} · {status} · score {score_txt} · {added}"
        expanded = expand_id == job.id
        with st.expander(header, expanded=expanded):
            top = st.columns([3, 1, 1])
            top[0].caption(f"{source} · ID `{job.id[:8]}…`")
            if top[1].button("Mission Control", key=f"lib_wb_{job.id}", use_container_width=True):
                go_to_home(job_id=job.id, step="role")
            with top[2]:
                st.markdown('<div class="or-delete-btn">', unsafe_allow_html=True)
                if st.button("Delete", key=f"lib_del_{job.id}", use_container_width=True):
                    _handle_delete(job.id)
                st.markdown("</div>", unsafe_allow_html=True)
            render_job_detail(job, show_actions=False)
            st.session_state["library_job_id"] = job.id
