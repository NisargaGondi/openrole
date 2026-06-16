"""Outreach draft review."""

import streamlit as st
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from openrole.agents.email_writer import EmailWriterError, draft_outreach_for_job
from openrole.db.models import Contact, Job, Outreach, OutreachStatus
from openrole.db.repository import list_contacts_for_job, list_outreach_drafts
from openrole.db.session import get_session_factory


def _job_options(factory) -> list[tuple[str, str]]:
    with factory() as session:
        jobs = list(
            session.scalars(
                select(Job)
                .options(joinedload(Job.company))
                .order_by(Job.created_at.desc())
                .limit(30)
            ).unique()
        )
    labels: list[tuple[str, str]] = []
    for job in jobs:
        company = job.company.name if job.company else "—"
        labels.append((f"{job.title} @ {company}", job.id))
    return labels


st.header("Outreach")
st.caption("Drafts only — nothing sends automatically. Mark reviewed when ready.")

factory = get_session_factory()
options = _job_options(factory)
job_filter = st.selectbox(
    "Filter by job",
    options=["All jobs"] + [o[0] for o in options],
)
job_id = None
if job_filter != "All jobs":
    for label, jid in options:
        if label == job_filter:
            job_id = jid
            break

if job_id:
    with factory() as session:
        job = session.get(Job, job_id)
        contacts = (
            list_contacts_for_job(
                session,
                company_id=job.company_id,
                source_job_id=job_id,
            )
            if job and job.company_id
            else []
        )
    st.subheader("Compose drafts")
    if not contacts:
        st.info("No contacts for this job yet — run **Find people** on the **Jobs** tab.")
    else:
        researched = sum(1 for c in contacts if c.research_brief)
        st.write(
            f"**{len(contacts)}** contact(s) for this role "
            f"({researched} already researched)."
        )
        if st.button("Compose drafts for all contacts", type="primary"):
            try:
                with st.spinner(
                    f"Researching (if needed) and drafting for {len(contacts)} contact(s)…"
                ):
                    result = draft_outreach_for_job(job_id=job_id, auto_research=True)
                if result.get("drafted_count"):
                    st.success(
                        f"Created/updated drafts for **{result['drafted_count']}** "
                        f"of {result['contact_count']} contact(s)."
                    )
                for row in result.get("drafted") or []:
                    st.caption(f"✓ {row['full_name']}")
                for row in result.get("skipped") or []:
                    st.warning(f"Skipped {row['name']}: {row['reason']}")
                for row in result.get("errors") or []:
                    st.error(f"{row['name']}: {row['error']}")
                for w in result.get("profile_warnings") or []:
                    st.warning(w)
                st.rerun()
            except EmailWriterError as exc:
                st.error(str(exc))
            except Exception as exc:
                st.error(f"Unexpected error: {exc}")
    st.divider()

with factory() as session:
    drafts = list_outreach_drafts(session, job_id=job_id, limit=50)

if not drafts:
    st.info(
        "No outreach drafts yet. Select a job above and click "
        "**Compose drafts for all contacts**, or use **Draft** on the **Jobs** tab."
    )
else:
    for row in drafts:
        with factory() as session:
            contact = session.get(Contact, row.contact_id)
            job = session.get(Job, row.job_id) if row.job_id else None
        title = f"{row.channel.value} — {contact.full_name if contact else row.contact_id}"
        if job:
            title += f" ({job.title})"
        with st.expander(title):
            if row.subject:
                subject = st.text_input("Subject", value=row.subject, key=f"sub_{row.id}")
            else:
                subject = None
            body = st.text_area("Body", value=row.body, height=220, key=f"body_{row.id}")
            cols = st.columns(3)
            if cols[0].button("Save edits", key=f"save_{row.id}"):
                with factory() as session:
                    db_row = session.get(Outreach, row.id)
                    if db_row:
                        db_row.subject = subject
                        db_row.body = body
                        session.commit()
                st.success("Saved")
            if cols[1].button("Mark reviewed", key=f"rev_{row.id}"):
                with factory() as session:
                    db_row = session.get(Outreach, row.id)
                    if db_row:
                        db_row.status = OutreachStatus.REVIEWED
                        session.commit()
                st.success("Marked reviewed")
            if job and job.source_url:
                cols[2].link_button("Job posting", job.source_url, key=f"job_{row.id}")
