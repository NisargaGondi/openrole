"""Tracker dashboard widgets."""

from __future__ import annotations

from typing import Any

import streamlit as st

from openrole.db.models import JOB_STATUS_LABELS, TRACKER_STATUS_ORDER, Job, JobStatus
from openrole.db.repository import get_job_notion_page_id, update_job_status
from openrole.sync.mappers import job_to_tracker_row
from openrole.sync.notion import notion_configured, sync_job_status_to_notion
from openrole.ui.navigation import go_to_home, go_to_job_library
from openrole.ui.theme import KANBAN_COLUMNS, job_card_html, kpi_tile


def render_kpi_row(stats: dict[str, Any], *, last_scout: dict[str, Any] | None) -> None:
    by = stats.get("jobs_by_status") or {}
    active = (
        by.get("applied", 0)
        + by.get("assessment", 0)
        + by.get("interviewing", 0)
        + by.get("waitlist", 0)
    )
    scout_sub = ""
    if last_scout:
        scout_sub = f"+{last_scout.get('ingested_new', 0)} last scout"
    cols = st.columns(4)
    tiles = [
        ("Total roles", stats.get("total_jobs", 0), "In your tracker"),
        ("Active pipeline", active, "Applied → interview"),
        ("Outreach drafts", stats.get("pending_outreach", 0), "Awaiting review"),
        ("ATS targets", stats.get("companies_with_scout_metadata", 0), scout_sub or "Company boards"),
    ]
    for col, (label, value, sub) in zip(cols, tiles, strict=True):
        with col:
            st.markdown(kpi_tile(label, value, sub), unsafe_allow_html=True)


def render_pipeline_chart(stats: dict[str, Any]) -> None:
    by = stats.get("jobs_by_status") or {}
    labels: list[str] = []
    values: list[int] = []
    colors: list[str] = []
    from openrole.ui.theme import STATUS_COLORS

    for key in TRACKER_STATUS_ORDER:
        count = by.get(key, 0)
        if count:
            labels.append(JOB_STATUS_LABELS.get(key, key))
            values.append(count)
            colors.append(STATUS_COLORS.get(key, "#6366f1"))
    if not labels:
        st.caption("Pipeline chart appears once you have tracked jobs.")
        return
    try:
        import altair as alt
        import pandas as pd

        df = pd.DataFrame({"status": labels, "count": values, "color": colors})
        chart = (
            alt.Chart(df)
            .mark_bar(cornerRadiusTopLeft=6, cornerRadiusTopRight=6)
            .encode(
                x=alt.X("status:N", sort=labels, title=None, axis=alt.Axis(labelAngle=-25)),
                y=alt.Y("count:Q", title="Roles"),
                color=alt.Color("color:N", scale=None, legend=None),
                tooltip=["status", "count"],
            )
            .properties(height=220)
        )
        st.altair_chart(chart, use_container_width=True)
    except Exception:
        st.bar_chart(dict(zip(labels, values, strict=True)), height=220)


def render_scout_trend(runs: list[dict[str, Any]]) -> None:
    if not runs:
        st.caption("Scout trend appears after your first run.")
        return
    rows = [
        {
            "run": (r.get("finished_at") or r.get("logged_at") or "")[:10],
            "new": r.get("ingested_new", 0),
            "seen_skip": r.get("skipped_already_seen", 0),
        }
        for r in reversed(runs[-8:])
    ]
    st.caption("Scout — new jobs per run")
    try:
        import altair as alt
        import pandas as pd

        df = pd.DataFrame(rows)
        chart = (
            alt.Chart(df)
            .mark_bar(color="#22c55e", cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
            .encode(
                x=alt.X("run:N", title=None),
                y=alt.Y("new:Q", title="New jobs"),
                tooltip=["run", "new", "seen_skip"],
            )
            .properties(height=160)
        )
        st.altair_chart(chart, use_container_width=True)
    except Exception:
        st.bar_chart({row["run"]: row["new"] for row in rows}, height=160)


def render_application_funnel(stats: dict[str, Any]) -> None:
    """Funnel-style view: discovered → applied → assessment → interview → offer."""
    by = stats.get("jobs_by_status") or {}
    stages = [
        ("Discovered", by.get("discovered", 0)),
        ("Applied", by.get("applied", 0)),
        ("Assessment", by.get("assessment", 0)),
        ("Interviewing", by.get("interviewing", 0)),
        ("Offer", by.get("offer", 0)),
    ]
    if sum(v for _, v in stages) == 0:
        return
    try:
        import altair as alt
        import pandas as pd

        df = pd.DataFrame(stages, columns=["stage", "count"])
        chart = (
            alt.Chart(df)
            .mark_bar(cornerRadiusTopLeft=5, cornerRadiusTopRight=5)
            .encode(
                x=alt.X("stage:N", sort=[s[0] for s in stages], title=None),
                y=alt.Y("count:Q", title="Roles"),
                color=alt.value("#818cf8"),
                tooltip=["stage", "count"],
            )
            .properties(height=180)
        )
        st.caption("Application funnel")
        st.altair_chart(chart, use_container_width=True)
    except Exception:
        pass


def render_kanban(jobs: list[Job], *, factory) -> None:
    st.markdown("##### Board")
    cols = st.columns(len(KANBAN_COLUMNS))
    for col, (_key, title, statuses) in zip(cols, KANBAN_COLUMNS, strict=True):
        group = [j for j in jobs if j.status.value in statuses]
        with col:
            st.markdown(
                f'<div class="or-kanban-title">{title} · {len(group)}</div>',
                unsafe_allow_html=True,
            )
            with st.container(border=True):
                if not group:
                    st.caption("No roles here yet")
                for job in group[:6]:
                    _render_job_card(job, factory=factory)
                if len(group) > 6:
                    st.caption(f"+{len(group) - 6} more below")


def render_jobs_table(jobs: list[Job], *, factory, status_filter: str) -> None:
    st.markdown("##### All roles")
    if not jobs:
        st.info("No roles yet — add one in **Job library** or run **Job scout**.")
        return

    for job in jobs:
        company = job.company.name if job.company else "—"
        scout = (job.raw_payload or {}).get("scout") or {}
        score = scout.get("relevance_score")
        with st.container(border=True):
            st.markdown(
                job_card_html(
                    title=job.title,
                    company=company,
                    score=score,
                    source=scout.get("source"),
                    status=job.status.value,
                ),
                unsafe_allow_html=True,
            )
            c1, c2, c3, c4 = st.columns([2, 2, 1, 1])
            status_options = list(TRACKER_STATUS_ORDER)
            idx = status_options.index(job.status.value) if job.status.value in status_options else 0
            new_status = c1.selectbox(
                "Status",
                options=status_options,
                index=idx,
                format_func=lambda s: JOB_STATUS_LABELS.get(s, s),
                key=f"tbl_status_{job.id}",
                label_visibility="collapsed",
            )
            if new_status != job.status.value:
                _apply_status_change(job.id, new_status, company=company, factory=factory)
            if job.source_url:
                c2.link_button("Posting", job.source_url, key=f"tbl_url_{job.id}")
            if c3.button("Details", key=f"tbl_lib_{job.id}", use_container_width=True):
                go_to_job_library(job_id=job.id)
            if c4.button("Control", key=f"tbl_pipe_{job.id}", use_container_width=True):
                go_to_home(job_id=job.id, step="people")


def _render_job_card(job: Job, *, factory) -> None:
    company = job.company.name if job.company else "—"
    scout = (job.raw_payload or {}).get("scout") or {}
    st.markdown(
        job_card_html(
            title=job.title[:48] + ("…" if len(job.title) > 48 else ""),
            company=company,
            score=scout.get("relevance_score"),
            source=scout.get("source"),
            status=job.status.value,
        ),
        unsafe_allow_html=True,
    )
    b1, b2 = st.columns(2)
    if b1.button("Details", key=f"kb_detail_{job.id}", use_container_width=True):
        go_to_job_library(job_id=job.id)
    if b2.button("Control", key=f"kb_{job.id}", use_container_width=True):
        go_to_home(job_id=job.id, step="people")


def _apply_status_change(job_id: str, new_status: str, *, company: str, factory) -> None:
    with factory() as session:
        updated = update_job_status(session, job_id, JobStatus(new_status))
        session.commit()
        if notion_configured():
            page_id = get_job_notion_page_id(updated)
            if page_id:
                row = job_to_tracker_row(updated, company_name=company)
                sync_job_status_to_notion(row, notion_page_id=page_id)
    st.rerun()
