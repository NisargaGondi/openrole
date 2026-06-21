"""Outreach — discovered contacts and draft review for a job."""

from __future__ import annotations

import streamlit as st

from openrole.agents.email_writer import EmailWriterError, draft_outreach_for_job
from openrole.db.models import Contact, Job, Outreach, OutreachStatus
from openrole.db.repository import list_contacts_for_job, list_outreach_drafts
from openrole.db.session import get_session_factory
from openrole.ui.components.contact_table import render_contact_table


def render_outreach_section(job_id: str) -> None:
    st.subheader("People found")
    st.caption("Apollo + CareerShift results for this role — review before drafting outreach.")

    contact_count = render_contact_table(job_id)

    st.divider()
    st.subheader("Outreach drafts")
    st.caption("Drafts only — nothing sends automatically.")

    factory = get_session_factory()
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

    if contacts and st.button("Compose drafts for all contacts", type="primary", key="wf_draft_all"):
        try:
            with st.spinner(f"Drafting for {len(contacts)} contact(s)…"):
                result = draft_outreach_for_job(job_id=job_id, auto_research=True)
            st.success(f"Drafted {result.get('drafted_count', 0)} contact(s).")
            st.rerun()
        except EmailWriterError as exc:
            st.error(str(exc))
    elif contact_count == 0:
        st.caption("Compose becomes available after people discovery finds contacts.")

    with factory() as session:
        drafts = list_outreach_drafts(session, job_id=job_id, limit=50)

    if not drafts:
        st.info("No drafts yet — run the **Workbench** outreach step, or compose above.")
        return

    for row in drafts:
        with factory() as session:
            contact = session.get(Contact, row.contact_id)
            job = session.get(Job, row.job_id) if row.job_id else None
        title = f"{row.channel.value} — {contact.full_name if contact else 'contact'}"
        with st.expander(title):
            subject = None
            if row.subject:
                subject = st.text_input("Subject", value=row.subject, key=f"wf_sub_{row.id}")
            body = st.text_area("Body", value=row.body, height=180, key=f"wf_body_{row.id}")
            cols = st.columns(2)
            if cols[0].button("Save", key=f"wf_save_{row.id}"):
                with factory() as session:
                    db_row = session.get(Outreach, row.id)
                    if db_row:
                        db_row.subject = subject
                        db_row.body = body
                        session.commit()
                st.success("Saved")
            if cols[1].button("Mark reviewed", key=f"wf_rev_{row.id}"):
                with factory() as session:
                    db_row = session.get(Outreach, row.id)
                    if db_row:
                        db_row.status = OutreachStatus.REVIEWED
                        session.commit()
                st.success("Reviewed")
            if job and job.source_url:
                st.link_button("Posting", job.source_url, key=f"wf_post_{row.id}")
