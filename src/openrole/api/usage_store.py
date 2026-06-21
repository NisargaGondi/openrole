"""API usage rates and message parsing."""

from __future__ import annotations

from openrole.api import activity_store

COST_PER_CALL: dict[str, float] = {
    "tavily": 0.008,
    "apollo": 0.03,
    "jobspy": 0.0,
    "handshake": 0.0,
    "careershift": 0.0,
    "notion": 0.0,
}

DEFAULT_LLM_COST_PER_CALL = 0.002


def cost_for_service(service: str) -> float:
    if service.startswith("llm/"):
        return DEFAULT_LLM_COST_PER_CALL
    return COST_PER_CALL.get(service, 0.0)


def detect_services_in_message(message: str) -> dict[str, int]:
    """Infer non-LLM API usage from log lines (LLM is tracked at invoke time)."""
    msg = message.lower()
    found: dict[str, int] = {}
    if "tavily" in msg:
        found["tavily"] = found.get("tavily", 0) + 1
    if "apollo" in msg:
        found["apollo"] = found.get("apollo", 0) + 1
    if "jobspy" in msg or "indeed" in msg or ("linkedin" in msg and "scout" in msg):
        found["jobspy"] = found.get("jobspy", 0) + 1
    if "handshake" in msg:
        found["handshake"] = found.get("handshake", 0) + 1
    if "careershift" in msg:
        found["careershift"] = found.get("careershift", 0) + 1
    if "notion" in msg:
        found["notion"] = found.get("notion", 0) + 1
    return found


def usage_summary_from_activity() -> dict:
    """Fallback: scan in-memory activity when DB has no events yet."""
    lines = activity_store.get_lines(500)
    counts: dict[str, int] = {k: 0 for k in COST_PER_CALL}
    for line in lines:
        for svc, n in detect_services_in_message(line.get("message") or "").items():
            counts[svc] = counts.get(svc, 0) + n

    services = []
    total = 0.0
    for key, rate in COST_PER_CALL.items():
        calls = counts.get(key, 0)
        cost = round(calls * cost_for_service(key), 4)
        total += cost
        services.append({"key": key, "calls": calls, "est_cost_usd": cost, "rate_usd": rate})

    return {
        "services": services,
        "total_est_cost_usd": round(total, 4),
        "activity_lines_scanned": len(lines),
        "event_count": 0,
        "by_job": [],
        "recent": [],
    }
