"""Environment and integration status."""

import streamlit as st

from openrole.config import get_settings
from openrole.scrapers.careershift_client import (
    is_ready as careershift_ready,
    patchright_installed as careershift_patchright_installed,
    profile_ready as careershift_profile_ready,
)
from openrole.scrapers.handshake_client import (
    handshake_mcp_installed,
    handshake_profile_ready,
    patchright_browser_ready,
)
from openrole.tools import apollo_client, jobspy_client
from openrole.tools.candidate_profile import profile_status

st.header("Settings")

settings = get_settings()

st.subheader("Core")
ingestion_model = (
    settings.vertex_model_ingestion
    if settings.llm_provider == "vertex"
    else settings.openai_model_ingestion
)
writing_model = (
    settings.vertex_model_writing
    if settings.llm_provider == "vertex"
    else settings.openai_model_writing
)
st.code(
    f"""APP_ENV={settings.app_env}
DATABASE={settings.masked_database_url()}
LLM_PROVIDER={settings.llm_provider}
INGESTION_MODEL={ingestion_model}
WRITING_MODEL={writing_model}
""",
    language="text",
)

st.subheader("Integrations")
rows = [
    (
        "Vertex AI (Gemini)",
        settings.vertex_ready,
        "GCP_PROJECT_ID + GOOGLE_APPLICATION_CREDENTIALS",
    ),
    (
        "OpenAI",
        settings.openai_configured,
        "OPENAI_API_KEY (+ optional OPENAI_API_BASE for OpenRouter)",
    ),
    ("JobSpy (LinkedIn / Indeed)", jobspy_client.is_available(), "bash scripts/install_jobspy.sh"),
    (
        "Handshake MCP (local stdio)",
        handshake_mcp_installed() and patchright_browser_ready() and handshake_profile_ready(),
        "bash scripts/install_handshake.sh && python scripts/handshake_login.py --clear-profile --force",
    ),
    (
        "CareerShift (local Playwright)",
        careershift_ready(),
        "bash scripts/install_careershift.sh && python scripts/careershift_login.py --clear-profile --force",
    ),
    ("Apollo.io", bool(settings.apollo_api_key), "APOLLO_API_KEY"),
    ("Tavily search", bool(settings.tavily_api_key), "TAVILY_API_KEY"),
    ("Notion sync", bool(settings.notion_api_key), "NOTION_API_KEY"),
]

for name, ok, env_key in rows:
    st.write(f"{'✓' if ok else '○'} **{name}** — `{env_key}`")

st.divider()
st.subheader("Candidate profile (outreach drafts)")
st.caption(
    "Set in `.env`: `CANDIDATE_NAME`, `CANDIDATE_RESUME_PATHS` (comma-separated), "
    "`CANDIDATE_LINKEDIN_URL`, `CANDIDATE_GITHUB_URL`, `CANDIDATE_WEBSITE_URL`, "
    "`CANDIDATE_GRADUATION`, `CANDIDATE_ROLE_SEARCH`"
)
status = profile_status()
st.write(f"**Name:** {'✓ ' + (get_settings().candidate_name or '') if status['name_set'] else '○ not set'}")
st.write(
    f"**Graduation:** "
    f"{'✓ ' + (get_settings().candidate_graduation or '') if status['graduation_set'] else '○ not set'}"
)
st.write(f"**Role search:** {status['role_search']}")
st.write(f"**LinkedIn:** {'✓' if status['linkedin_set'] else '○'}")
st.write(f"**GitHub:** {'✓' if status['github_set'] else '○'}")
st.write(f"**Website:** {'✓' if status['website_set'] else '○'}")
st.write(
    f"**Resumes:** {status['resume_files_found']}/{len(status['resume_paths'])} files found"
)
if status["resume_paths"]:
    for p in status["resume_paths"]:
        st.code(p, language="text")
if status["warnings"]:
    for w in status["warnings"]:
        st.warning(w)
elif status["has_prompt_context"]:
    st.success("Profile context ready for draft generation.")

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

if apollo_client.is_configured():
    if st.button("Test Apollo (people search)"):
        with st.spinner("Calling Apollo…"):
            result = apollo_client.probe_apollo()
        if result.get("ok"):
            st.success(f"Apollo OK — sample search returned {result['count']} rows")
            st.json(result.get("sample"))
        else:
            st.error(result.get("error", "Apollo failed"))
else:
    st.caption("Apollo: set APOLLO_API_KEY to enable people discovery.")

if careershift_ready():
    if st.button("Test CareerShift (contact search)"):
        with st.spinner("Searching CareerShift (opens browser on macOS)…"):
            from openrole.scrapers import careershift_client

            result = careershift_client.probe_careershift(company_name="Cadence")
        if result.get("ok"):
            st.success(f"CareerShift OK — sample search returned {result['count']} rows")
            st.json(result.get("sample"))
        else:
            st.error(result.get("error", "CareerShift failed"))
            st.caption("Debug: `python scripts/careershift_inspect.py` dumps search field selectors.")
elif careershift_patchright_installed() and patchright_browser_ready() and not careershift_profile_ready():
    st.warning("CareerShift Chromium is ready but you are not logged in yet.")

st.divider()
st.markdown(
    """
**Handshake security:** OpenRole talks to Handshake only via a **local MCP subprocess**
(`python -m handshake_mcp_server`). Your login cookies stay in `~/.handshake-mcp/profile`
on your machine — nothing is sent to a third-party MCP host.

On macOS, OpenRole starts the MCP browser in **headed mode** (a Chrome window may flash briefly)
so Cloudflare does not block scraping.

One-time setup (installs Patchright Chromium + login):
```bash
bash scripts/install_handshake.sh
python scripts/handshake_login.py --clear-profile --force
```
Use `scripts/handshake_login.py` (not `handshake_mcp_server --login`). If Chrome closes instantly,
the old profile had a false-positive session — run with `--clear-profile --force`.

**CareerShift security:** Same local-only model. Login cookies stay in
`~/.openrole/careershift/profile` on your machine.

One-time CareerShift setup:
```bash
bash scripts/install_careershift.sh
python scripts/careershift_login.py --clear-profile --force
```
CMU signup (if needed): https://www.careershift.com/user/signup?group=CMU
"""
)

if handshake_mcp_installed() and not patchright_browser_ready():
    st.error(
        "Patchright Chromium is not installed — login will fail with "
        "'Executable doesn't exist'. Run: `bash scripts/install_handshake.sh`"
    )
elif handshake_mcp_installed() and not handshake_profile_ready():
    st.warning("Handshake MCP is installed but you are not logged in yet.")

st.caption("Restart Streamlit after editing `.env`.")
