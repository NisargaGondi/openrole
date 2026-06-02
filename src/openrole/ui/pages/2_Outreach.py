"""Outreach draft review (milestone 3)."""

import streamlit as st

from sqlalchemy import select

from openrole.db.models import Outreach
from openrole.db.session import get_session_factory

st.header("Outreach")
st.info("Draft review UI connects in milestone 3. Nothing sends automatically.")

factory = get_session_factory()
with factory() as session:
    drafts = list(
        session.scalars(
            select(Outreach).order_by(Outreach.created_at.desc()).limit(50)
        ).all()
    )

if not drafts:
    st.write("No outreach drafts yet.")
else:
    for row in drafts:
        with st.expander(f"{row.channel.value} — {row.status.value}"):
            if row.subject:
                st.markdown(f"**Subject:** {row.subject}")
            st.text(row.body)
