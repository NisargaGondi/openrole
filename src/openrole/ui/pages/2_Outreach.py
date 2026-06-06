"""Outreach draft review."""

import streamlit as st
from sqlalchemy import select

from openrole.db.models import Contact, Job, Outreach, OutreachStatus
from openrole.db.repository import list_outreach_drafts
from openrole.db.session import get_session_factory


def _job_options(factory) -> list[tuple[str, str]]:
    with factory() as session:
        jobs = list(session.scalars(select(Job).order_by(Job.created_at.desc()).limit(30)))
    return [(f"{j.title}", j.id) for j in jobs]


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

with factory() as session:
    drafts = list_outreach_drafts(session, job_id=job_id, limit=50)

if not drafts:
    st.info("No outreach drafts yet. Run **Research** and **Draft outreach** from the Jobs page.")
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
