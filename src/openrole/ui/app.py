"""OpenRole Streamlit dashboard entrypoint."""

import streamlit as st

from openrole import __version__
from openrole.config import get_settings
from openrole.db.session import init_db

st.set_page_config(
    page_title="OpenRole",
    page_icon="◉",
    layout="wide",
    initial_sidebar_state="expanded",
)

settings = get_settings()


@st.cache_resource
def _ensure_db() -> bool:
    init_db()
    return True


_ensure_db()

st.title("OpenRole")
st.caption(f"v{__version__} — research first, send second")

col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Environment", settings.app_env)
with col2:
    st.metric("Database", "SQLite" if settings.is_sqlite else "PostgreSQL")
with col3:
    st.metric("Vertex AI", "ready" if settings.vertex_configured else "not configured")

st.divider()

st.markdown(
    """
### Week 1 foundation

Use the sidebar pages:

- **Jobs** — ingest and review roles (coming in milestone 1)
- **Outreach** — review email and LinkedIn drafts (milestone 3)
- **Settings** — environment and integration status

### Quick test (stub pipeline)

Paste a job URL to exercise the placeholder LangGraph (no real scraping yet).
"""
)

from openrole.graph.main_graph import run_pipeline

job_url = st.text_input("Job URL (optional)")
job_text = st.text_area("Or paste job description", height=120)

if st.button("Run stub pipeline", type="primary"):
    result = run_pipeline(job_url=job_url or None, job_text=job_text or None)
    st.json(result)
