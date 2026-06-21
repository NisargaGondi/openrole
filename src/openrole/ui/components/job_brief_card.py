"""Glass job brief card — center panel under network graph."""

from __future__ import annotations

import streamlit as st

from openrole.db.models import Job
from openrole.ui.theme import STATUS_COLORS


def render_job_brief_card(job: Job) -> None:
    company = job.company.name if job.company else "—"
    scout = (job.raw_payload or {}).get("scout") or {}
    score = scout.get("relevance_score")
    status = job.status.value.replace("_", " ").title()
    color = STATUS_COLORS.get(job.status.value, "#6366f1")
    score_badge = f'<span class="or-sig-score">{score}</span>' if score is not None else ""
    opt = scout.get("opt_status") or scout.get("accepts_opt")
    opt_badge = ""
    if opt:
        opt_badge = f'<span class="or-sig-opt">OPT</span>'
    st.markdown(
        f'<div class="or-sig-brief">'
        f'<div class="or-sig-brief-top">'
        f'<span class="or-sig-brief-co">{company}</span>{score_badge}{opt_badge}'
        f"</div>"
        f'<div class="or-sig-brief-title">{job.title}</div>'
        f'<div class="or-sig-brief-meta">'
        f'<span class="or-status-dot" style="background:{color};"></span>{status}'
        f"</div></div>",
        unsafe_allow_html=True,
    )
