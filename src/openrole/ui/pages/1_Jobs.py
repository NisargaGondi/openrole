"""Jobs list and ingestion (milestone 1)."""

import streamlit as st

from sqlalchemy import select

from openrole.db.models import Job
from openrole.db.session import get_session_factory

st.header("Jobs")
st.info("Job ingestion (JobSpy, ATS APIs) lands in milestone 1.")

factory = get_session_factory()
with factory() as session:
    jobs = list(
        session.scalars(select(Job).order_by(Job.created_at.desc()).limit(50)).all()
    )

if not jobs:
    st.write("No jobs in the database yet.")
else:
    for job in jobs:
        with st.expander(f"{job.title} — {job.status.value}"):
            st.write(f"**Company ID:** {job.company_id or '—'}")
            st.write(f"**Source:** {job.source_platform or '—'}")
            if job.source_url:
                st.link_button("View posting", job.source_url)
