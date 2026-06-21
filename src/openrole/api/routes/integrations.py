"""Integration probes and browser login triggers."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from openrole.api.activity_store import log as act_log
from openrole.integrations.browser_login import run_careershift_login, run_handshake_login
from openrole.tools import apollo_client, jobspy_client
from openrole.scrapers import careershift_client

router = APIRouter(tags=["integrations"])


@router.post("/integrations/test/{service}")
def test_integration(service: str):
    act_log(f"Testing {service}…", icon="radar")
    if service == "jobspy_indeed":
        result = jobspy_client.probe_jobspy(site="indeed")
    elif service == "jobspy_linkedin":
        result = jobspy_client.probe_jobspy(site="linkedin")
    elif service == "apollo":
        if not apollo_client.is_configured():
            raise HTTPException(400, "APOLLO_API_KEY not set")
        result = apollo_client.probe_apollo()
    elif service == "careershift":
        if not careershift_client.is_ready():
            raise HTTPException(400, "CareerShift not ready — run login first")
        result = careershift_client.probe_careershift(company_name="Cadence")
    else:
        raise HTTPException(404, f"Unknown test: {service}")

    if result.get("ok"):
        act_log(f"{service} test OK", level="ok", icon="check")
    else:
        act_log(f"{service} test failed: {result.get('error')}", level="err", icon="alert")
    return result


@router.post("/integrations/login/{provider}")
def browser_login(provider: str, clear_profile: bool = Query(False)):
    """Open browser for Handshake or CareerShift login (local machine only)."""
    act_log(f"Starting {provider} browser login…", icon="radar")
    if provider == "careershift":
        ok, msg = run_careershift_login(force=True, clear_profile=clear_profile)
    elif provider == "handshake":
        ok, msg = run_handshake_login(force=True, clear_profile=clear_profile)
    else:
        raise HTTPException(404, "Unknown provider")

    if ok:
        act_log(f"{provider} login OK", level="ok", icon="check")
    else:
        act_log(f"{provider} login failed: {msg}", level="err", icon="alert")
    return {"ok": ok, "message": msg}
