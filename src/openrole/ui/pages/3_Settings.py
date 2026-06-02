"""Environment and integration status."""

import streamlit as st

from openrole.config import get_settings

st.header("Settings")

settings = get_settings()

st.subheader("Core")
st.code(
    f"""APP_ENV={settings.app_env}
DATABASE={settings.masked_database_url()}
VERTEX={settings.vertex_configured} ({settings.vertex_model_default})
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
    ("Apollo.io", bool(settings.apollo_api_key), "APOLLO_API_KEY"),
    ("OpenAI (fallback)", bool(settings.openai_api_key), "OPENAI_API_KEY"),
    ("Tavily search", bool(settings.tavily_api_key), "TAVILY_API_KEY"),
    ("Notion sync", bool(settings.notion_api_key), "NOTION_API_KEY"),
]

for name, ok, env_key in rows:
    st.write(f"{'✓' if ok else '○'} **{name}** — `{env_key}`")

st.caption("Copy `.env.example` to `.env` in the repo root and restart Streamlit after changes.")
