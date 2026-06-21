"""Resume fit and application answers for a job."""

from __future__ import annotations

import streamlit as st
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from openrole.agents.app_assistant import ApplicationAssistantError, draft_application_answers, get_application_draft
from openrole.agents.resume_optimizer import (
    ResumeOptimizerError,
    get_job_resume_analyses,
    optimize_all_resumes_for_job,
    optimize_resume_for_job,
)
from openrole.db.models import Job
from openrole.db.repository import list_resumes
from openrole.db.session import get_session_factory


def _render_report(report: dict) -> None:
    score = report.get("match_score")
    if score is not None:
        st.metric("Match score", f"{score}/100")
    if report.get("summary"):
        st.write(report["summary"])
    for key in ("strengths", "gaps", "missing_keywords", "ats_risks"):
        items = report.get(key)
        if items:
            st.markdown(f"**{key.replace('_', ' ').title()}**")
            if isinstance(items, list):
                for item in items:
                    st.write(f"- {item}")
            else:
                st.write(items)


def render_apply_section(job_id: str) -> None:
    factory = get_session_factory()
    with factory() as session:
        job = session.scalar(
            select(Job).options(joinedload(Job.company)).where(Job.id == job_id)
        )
        resumes = list_resumes(session)

    if job is None:
        st.error("Job not found.")
        return

    tab_resume, tab_apply = st.tabs(["Resume fit", "Application Q&A"])
    resume_labels = [r.label for r in resumes]

    with tab_resume:
        if not resumes:
            st.warning("Set `CANDIDATE_RESUME_PATHS` in `.env`.")
        else:
            pick = st.selectbox("Resume", ["All resumes"] + resume_labels, key="wf_res_pick")
            if st.button("Run ATS analysis", type="primary", key="wf_res_run"):
                try:
                    with st.spinner("Analyzing…"):
                        if pick == "All resumes":
                            result = optimize_all_resumes_for_job(job_id)
                            for report in result["reports"]:
                                _render_report(report)
                        else:
                            result = optimize_resume_for_job(job_id=job_id, resume_label=pick)
                            _render_report(result["report"])
                except ResumeOptimizerError as exc:
                    st.error(str(exc))
            try:
                saved = get_job_resume_analyses(job_id)
                for label, report in (saved or {}).items():
                    with st.expander(f"{label} — {report.get('match_score', '?')}/100"):
                        _render_report(report)
            except ResumeOptimizerError:
                pass

    with tab_apply:
        resume_for_apply = st.selectbox(
            "Resume",
            options=resume_labels if resume_labels else ["—"],
            key="wf_apply_res",
        )
        questions_text = st.text_area("Questions (one per line)", height=120, key="wf_apply_q")
        if st.button("Draft answers", key="wf_apply_draft"):
            lines = [ln.strip() for ln in questions_text.splitlines() if ln.strip()]
            try:
                out = draft_application_answers(
                    job_id=job_id,
                    questions=lines,
                    resume_label=resume_for_apply if resume_for_apply != "—" else None,
                )
                st.success("Draft saved below.")
                for item in out.get("draft", {}).get("answers") or []:
                    with st.expander(item.get("question", "Q")):
                        st.write(item.get("answer", ""))
            except ApplicationAssistantError as exc:
                st.error(str(exc))
        existing = get_application_draft(job_id)
        if existing:
            st.divider()
            for item in existing.get("answers") or []:
                with st.expander(item.get("question", "Q")):
                    st.write(item.get("answer", ""))
