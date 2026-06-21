"""Integration status."""

from fastapi import APIRouter

from openrole.config import get_settings
from openrole.scrapers.careershift_client import is_ready as careershift_ready
from openrole.scrapers.handshake_client import (
    handshake_mcp_installed,
    handshake_profile_ready,
    patchright_browser_ready,
)
from openrole.tools import apollo_client, jobspy_client
from openrole.api.usage_store import usage_summary_from_activity
from openrole.api.usage_tracker import usage_summary_persisted
from openrole.tools.candidate_profile import profile_status

router = APIRouter(tags=["settings"])


@router.get("/settings")
def settings_status():
    s = get_settings()
    return {
        "app_env": s.app_env,
        "llm_provider": s.resolved_llm_provider,
        "llm_models": s.llm_models_summary(),
        "integrations": [
            {"key": "vertex", "name": "Vertex AI", "ok": s.vertex_ready and s.gcp_credentials_ready},
            {"key": "fireworks", "name": "Fireworks", "ok": s.fireworks_configured},
            {"key": "jobspy", "name": "JobSpy", "ok": jobspy_client.is_available()},
            {
                "key": "handshake",
                "name": "Handshake",
                "ok": handshake_mcp_installed() and patchright_browser_ready() and handshake_profile_ready(),
            },
            {"key": "careershift", "name": "CareerShift", "ok": careershift_ready()},
            {"key": "apollo", "name": "Apollo", "ok": s.apollo_enabled and apollo_client.is_configured()},
            {"key": "tavily", "name": "Tavily", "ok": bool(s.tavily_api_key)},
            {"key": "notion", "name": "Notion", "ok": bool(s.notion_api_key)},
        ],
        "profile": profile_status(),
        "careershift_daemon": _careershift_daemon_status(),
        "handshake_daemon": _handshake_daemon_status(),
        "browser_daemon_on_demand": _browser_daemon_on_demand(),
        "usage": _merged_usage(),
    }


def _browser_daemon_on_demand() -> bool:
    from openrole.scrapers.daemon_manager import on_demand_enabled

    return on_demand_enabled()


def _handshake_daemon_status() -> dict:
    from openrole.scrapers.handshake_ipc import (
        SOCKET_PATH,
        daemon_mode,
        daemon_pid,
        daemon_running,
    )

    running = daemon_running()
    info: dict = {
        "mode": daemon_mode(),
        "running": running,
        "pid": daemon_pid(),
        "socket": str(SOCKET_PATH),
    }
    if running:
        try:
            from openrole.scrapers.handshake_ipc import ping_daemon

            info.update(ping_daemon(timeout_s=2.0))
        except Exception:
            pass
    return info


def _careershift_daemon_status() -> dict:
    from openrole.scrapers.careershift_ipc import (
        SOCKET_PATH,
        daemon_mode,
        daemon_pid,
        daemon_running,
    )

    running = daemon_running()
    info: dict = {
        "mode": daemon_mode(),
        "running": running,
        "pid": daemon_pid(),
        "socket": str(SOCKET_PATH),
    }
    if running:
        try:
            from openrole.scrapers.careershift_ipc import ping_daemon

            info.update(ping_daemon(timeout_s=2.0))
        except Exception:
            pass
    return info


def _merged_usage() -> dict:
    persisted = usage_summary_persisted()
    if persisted.get("event_count", 0) > 0:
        return persisted
    return usage_summary_from_activity()
