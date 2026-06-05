"""Environment and integration status."""

import streamlit as st

from openrole.config import get_settings
from openrole.scrapers.handshake_client import (
    handshake_mcp_installed,
    handshake_profile_ready,
)
from openrole.tools import jobspy_client

st.header("Settings")

settings = get_settings()

st.subheader("Core")
st.code(
    f"""APP_ENV={settings.app_env}
DATABASE={settings.masked_database_url()}
INGESTION_MODEL={settings.vertex_model_ingestion}
WRITING_MODEL={settings.vertex_model_writing}
""",
    language="text",
)

st.subheader("Integrations")
rows = [
    (
        "Vertex AI (Gemini)",
        settings.vertex_configured and settings.gcp_credentials_ready,
        "GCP_PROJECT_ID + GOOGLE_APPLICATION_CREDENTIALS",
    ),
    ("JobSpy (LinkedIn / Indeed)", jobspy_client.is_available(), "bash scripts/install_jobspy.sh"),
    (
        "Handshake MCP (local stdio)",
        handshake_mcp_installed() and handshake_profile_ready(),
        "pip install 'openrole[handshake]' + python -m handshake_mcp_server --login",
    ),
    ("Apollo.io", bool(settings.apollo_api_key), "APOLLO_API_KEY"),
    ("OpenAI (fallback)", bool(settings.openai_api_key), "OPENAI_API_KEY"),
    ("Tavily search", bool(settings.tavily_api_key), "TAVILY_API_KEY"),
    ("Notion sync", bool(settings.notion_api_key), "NOTION_API_KEY"),
]

for name, ok, env_key in rows:
    st.write(f"{'✓' if ok else '○'} **{name}** — `{env_key}`")

st.divider()
st.subheader("Diagnostics")

col1, col2 = st.columns(2)
with col1:
    if st.button("Test JobSpy (Indeed)"):
        with st.spinner("Calling JobSpy…"):
            result = jobspy_client.probe_jobspy(site="indeed")
        if result.get("ok"):
            st.success(f"Indeed OK — {result['count']} rows")
            st.json(result.get("sample"))
        else:
            st.error(result.get("error", "JobSpy failed"))

with col2:
    if st.button("Test JobSpy (LinkedIn)"):
        with st.spinner("Calling JobSpy…"):
            result = jobspy_client.probe_jobspy(site="linkedin")
        if result.get("ok"):
            st.success(f"LinkedIn OK — {result['count']} rows")
            st.json(result.get("sample"))
        else:
            st.error(result.get("error", "JobSpy failed"))

st.markdown(
    """
**Handshake security:** OpenRole talks to Handshake only via a **local MCP subprocess**
(`python -m handshake_mcp_server`). Your login cookies stay in `~/.handshake-mcp/profile`
on your machine — nothing is sent to a third-party MCP host.

One-time login:
```bash
pip install 'openrole[handshake]'
python -m handshake_mcp_server --login --no-headless
```
"""
)

if handshake_mcp_installed() and not handshake_profile_ready():
    st.warning("Handshake MCP is installed but you are not logged in yet.")

st.caption("Restart Streamlit after editing `.env`.")
