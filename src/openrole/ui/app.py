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
Use the sidebar:

- **Jobs** — ingest URLs (Greenhouse, Lever, Ashby, LinkedIn, Indeed) and view saved roles
- **Outreach** — review email and LinkedIn drafts
- **Apply** — resume fit / ATS analysis and application question drafts
- **Pipeline** — run the full LangGraph workflow with review gates
- **Settings** — API keys, candidate profile, and integration status
"""
)
