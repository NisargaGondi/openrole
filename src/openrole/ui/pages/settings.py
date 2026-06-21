"""Environment and integration status."""

import streamlit as st

from openrole.config import clear_settings_cache, get_settings
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
from openrole.ui.components.integrations_bar import render_integrations_bar
from openrole.ui.components.integration_tiles import render_integration_tiles
from openrole.ui.components.page_header import render_page_header

render_page_header("settings")
render_integrations_bar(compact=False)

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
tile_rows = [
    ("vertex", "Vertex AI (Gemini)", settings.vertex_configured and settings.gcp_credentials_ready, "GCP_PROJECT_ID"),
    ("jobspy", "JobSpy", jobspy_client.is_available(), "install_jobspy.sh"),
    (
        "handshake",
        "Handshake MCP",
        handshake_mcp_installed() and patchright_browser_ready() and handshake_profile_ready(),
        "handshake_login.py",
    ),
    ("careershift", "CareerShift", careershift_ready(), "careershift_login.py"),
    ("apollo", "Apollo.io", bool(settings.apollo_api_key), "APOLLO_API_KEY"),
    ("tavily", "Tavily", bool(settings.tavily_api_key), "TAVILY_API_KEY"),
    ("notion", "Notion", bool(settings.notion_api_key), "NOTION_API_KEY"),
    ("fireworks", "Fireworks AI", settings.fireworks_configured, "FIREWORKS_API_KEY"),
]
render_integration_tiles(tile_rows)

st.divider()
st.subheader("All integrations")
rows = [
    (
        "Vertex AI (Gemini)",
        settings.vertex_configured and settings.gcp_credentials_ready,
        "GCP_PROJECT_ID + GOOGLE_APPLICATION_CREDENTIALS",
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
    ("OpenAI (fallback)", bool(settings.openai_api_key), "OPENAI_API_KEY"),
    ("Tavily search", bool(settings.tavily_api_key), "TAVILY_API_KEY — student plan via support@tavily.com"),
    ("Notion sync", bool(settings.notion_api_key), "NOTION_API_KEY"),
]

for name, ok, env_key in rows:
    st.write(f"{'✓' if ok else '○'} **{name}** — `{env_key}`")

st.divider()
st.subheader("Company targets (ATS boards)")
from openrole.config import _REPO_ROOT
from openrole.db.seed_companies import count_scout_target_companies, seed_companies_from_file

_counts = count_scout_target_companies()
st.write(
    f"**{ _counts['with_scout_metadata'] }** companies with ATS/careers metadata "
    f"(of {_counts['total']} total in DB)"
)
_targets_path = _REPO_ROOT / "data" / "scout_targets.yaml"
st.caption(f"Starter list: `{_targets_path.relative_to(_REPO_ROOT)}` — edit tiers/tokens, then seed.")
if st.button("Seed companies from scout_targets.yaml", type="secondary"):
    try:
        result = seed_companies_from_file(_targets_path)
        st.success(
            f"Upserted {result['upserted']} companies "
            f"({result['with_scout_metadata']} with ATS metadata)"
        )
        st.rerun()
    except Exception as exc:
        st.error(str(exc))
st.code("python scripts/seed_companies.py data/scout_targets.yaml", language="bash")

st.divider()
st.subheader("Notion sync")
st.caption(
    "Set `NOTION_API_KEY` and `NOTION_JOBS_DATABASE_ID`. "
    "Map property names to your database columns:"
)
st.code(
    f"""NOTION_PROP_TITLE={settings.notion_prop_title}
NOTION_PROP_COMPANY={settings.notion_prop_company}
NOTION_PROP_URL={settings.notion_prop_url}
NOTION_PROP_SCORE={settings.notion_prop_score}
NOTION_PROP_STATUS={settings.notion_prop_status}
# Optional:
# NOTION_PROP_SOURCE=Source
# NOTION_PROP_OPT=OPT Status""",
    language="text",
)

st.divider()
st.subheader("Job Scout")
from openrole.scheduler.scout_log import last_scout_run, load_scout_runs

_last = last_scout_run()
if _last:
    st.write(
        f"Last scout: **{( _last.get('finished_at') or _last.get('logged_at') or '')[:19]}** "
        f"({ _last.get('trigger', '?')}) — "
        f"{_last.get('ingested_new', 0)} new jobs · resume `{_last.get('resume_label', '—')}`"
    )
else:
    st.write("No scout runs logged yet.")
st.code(
    "# Cron example (Mon/Wed/Fri 9am):\n"
    "0 9 * * 1,3,5 cd /path/to/openrole && "
    "python scripts/run_scheduled_scout.py --resume-label 'YOUR_RESUME.pdf'",
    language="bash",
)

st.divider()
st.subheader("Candidate profile (outreach drafts)")
st.caption(
    "Set in `.env`: `CANDIDATE_NAME`, `CANDIDATE_RESUME_PATHS` (comma-separated), "
    "`CANDIDATE_LINKEDIN_URL`, `CANDIDATE_GITHUB_URL`, `CANDIDATE_WEBSITE_URL`"
)
status = profile_status()
st.write(f"**Name:** {'✓ ' + (get_settings().candidate_name or '') if status['name_set'] else '○ not set'}")
st.write(f"**LinkedIn:** {'✓' if status['linkedin_set'] else '○'}")
st.write(f"**GitHub:** {'✓' if status['github_set'] else '○'}")
st.write(f"**Website:** {'✓' if status['website_set'] else '○'}")
st.write(
    f"**Resumes:** {status['resume_files_found']}/{len(status['resume_paths'])} files found on disk"
)
if st.button("Reload resumes from .env", type="secondary"):
    clear_settings_cache()
    from openrole.db.repository import sync_resumes_from_env
    from openrole.db.session import session_scope

    with session_scope() as session:
        synced = sync_resumes_from_env(session)
    st.success(f"Reloaded {len(synced)} resume(s) from .env")
    st.rerun()
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
