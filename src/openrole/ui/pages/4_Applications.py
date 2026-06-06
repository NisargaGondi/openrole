"""Resume optimization and application question drafts per job."""

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
    if report.get("strengths"):
        st.markdown("**Strengths**")
        for s in report["strengths"]:
            st.write(f"- {s}")
    if report.get("gaps"):
        st.markdown("**Gaps**")
        for g in report["gaps"]:
            st.write(f"- {g}")
    if report.get("missing_keywords"):
        st.markdown("**Missing keywords (ATS)**")
        st.write(", ".join(f"`{k}`" for k in report["missing_keywords"]))
    if report.get("ats_risks"):
        st.markdown("**ATS risks**")
        for r in report["ats_risks"]:
            st.write(f"- {r}")
    edits = report.get("suggested_edits") or []
    if edits:
        st.markdown("**Suggested edits**")
        for e in edits:
            if isinstance(e, dict):
                st.write(f"**{e.get('section', 'General')}** — {e.get('issue', '')}")
                st.caption(e.get("suggestion", ""))
            else:
                st.write(str(e))


def _render_application_draft(draft: dict, *, job_id: str) -> None:
    if draft.get("tone_notes"):
        st.info(draft["tone_notes"])
    for idx, item in enumerate(draft.get("answers") or []):
        q = item.get("question", "Question")
        with st.expander(q, expanded=True):
            st.text_area(
                "Answer",
                value=item.get("answer") or "",
                height=140,
                key=f"ans_{job_id}_{idx}",
            )
            if item.get("notes"):
                st.caption(item["notes"])


st.header("Apply")
st.caption("Resume fit check and application question drafts — review before submitting.")

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
    resumes = list_resumes(session)

if not jobs:
    st.info("Ingest a job first on the **Jobs** tab.")
    st.stop()

if not resumes:
    st.warning(
        "No resumes found. Set `CANDIDATE_RESUME_PATHS` in `.env` "
        "(comma-separated paths to .pdf, .md, or .txt files)."
    )

job_options = {f"{j.title} @ {(j.company.name if j.company else '—')}": j.id for j in jobs}
selected_label = st.selectbox("Job", options=list(job_options.keys()))
job_id = job_options[selected_label]
job = next(j for j in jobs if j.id == job_id)

st.write(f"**Department:** {job.department or '—'}")
st.write(f"**Locations:** {', '.join(job.locations or []) or '—'}")
if job.source_url:
    st.link_button("View posting", job.source_url)

tab_resume, tab_apply = st.tabs(["Resume optimizer", "Application questions"])

resume_labels = [r.label for r in resumes] if resumes else []

with tab_resume:
    st.subheader("Resume vs job description")
    if not resumes:
        st.stop()

    pick = st.selectbox("Resume variant", options=["All resumes"] + resume_labels)

    if st.button("Run ATS / fit analysis", type="primary"):
        try:
            with st.spinner("Analyzing resume against JD…"):
                if pick == "All resumes":
                    result = optimize_all_resumes_for_job(job_id)
                    for report in result["reports"]:
                        _render_report(report)
                    for w in result.get("warnings") or []:
                        st.warning(w)
                else:
                    result = optimize_resume_for_job(job_id=job_id, resume_label=pick)
                    _render_report(result["report"])
                    for w in result.get("profile_warnings") or []:
                        st.warning(w)
        except ResumeOptimizerError as exc:
            st.error(str(exc))

    st.divider()
    st.subheader("Saved analyses")
    try:
        saved = get_job_resume_analyses(job_id)
    except ResumeOptimizerError as exc:
        st.error(str(exc))
        saved = {}
    if not saved:
        st.write("No saved analyses yet.")
    else:
        for label, report in saved.items():
            with st.expander(f"{label} — score {report.get('match_score', '?')}/100"):
                _render_report(report)

with tab_apply:
    st.subheader("Application question drafts")
    st.caption("Paste questions from the application form (one per line).")

    resume_for_apply = st.selectbox(
        "Resume to use",
        options=resume_labels if resume_labels else ["—"],
        key="apply_resume",
    )
    questions_text = st.text_area(
        "Questions",
        height=160,
        placeholder="Why do you want to work here?\nDescribe a project using Python and ML.\n",
    )
    if st.button("Draft answers"):
        lines = [ln.strip() for ln in questions_text.splitlines() if ln.strip()]
        try:
            with st.spinner("Drafting answers…"):
                out = draft_application_answers(
                    job_id=job_id,
                    questions=lines,
                    resume_label=resume_for_apply if resume_for_apply != "—" else None,
                )
            for w in out.get("profile_warnings") or []:
                st.warning(w)
            st.success("Draft saved — edit below and copy into the application form.")
            _render_application_draft(out["draft"], job_id=job_id)
        except ApplicationAssistantError as exc:
            st.error(str(exc))

    existing = get_application_draft(job_id)
    if existing:
        st.divider()
        st.subheader("Latest saved draft")
        _render_application_draft(existing, job_id=job_id)
