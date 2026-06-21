"""Job library — role constellation + ingest."""

from __future__ import annotations

import streamlit as st

from openrole.db.session import get_session_factory
from openrole.ui.components.activity_log import render_activity_log_panel
from openrole.ui.components.job_library import render_job_library
from openrole.ui.components.page_header import render_page_header
from openrole.ui.sections.ingest_section import render_ingest_section

render_page_header("library")

preselect = st.session_state.get("library_job_id")
main_col, log_col = st.columns([2.5, 1])

with main_col:
    st.markdown('<div class="or-sig-panel">', unsafe_allow_html=True)
    st.markdown("##### Ingest signal")
    render_ingest_section(key_prefix="lib")
    st.markdown("</div>")
    st.divider()
    render_job_library(factory=get_session_factory(), preselect_id=preselect)

with log_col:
    render_activity_log_panel()
