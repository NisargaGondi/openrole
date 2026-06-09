"""Extract office locations and department/team from job title + description."""

from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from openrole.config import get_settings
from openrole.db.models import Job
from openrole.llm import get_chat_model
from openrole.schemas.job_context import JobSearchContext

# Common US cities when JD lists multi-site roles in prose.
_CITY_ALIASES = {
    "san jose": "San Jose, CA",
    "austin": "Austin, TX",
    "new york": "New York, NY",
    "nyc": "New York, NY",
    "seattle": "Seattle, WA",
    "san francisco": "San Francisco, CA",
    "sf": "San Francisco, CA",
    "boston": "Boston, MA",
    "chicago": "Chicago, IL",
    "los angeles": "Los Angeles, CA",
    "denver": "Denver, CO",
    "atlanta": "Atlanta, GA",
    "pittsburgh": "Pittsburgh, PA",
    "remote us": "Remote, US",
}


def build_job_search_context(job: Job) -> JobSearchContext:
    """Build search context from stored fields + optional LLM pass on description."""
    base = JobSearchContext(
        office_locations=list(job.locations or []),
        department_name=job.department,
    )
    if not job.description or not get_settings().llm_configured:
        return _heuristic_context(job, base)

    try:
        extracted = _extract_with_llm(
            title=job.title,
            description=job.description,
            existing_locations=job.locations or [],
            existing_department=job.department,
        )
        return extracted.merge_stored(locations=job.locations, department=job.department)
    except Exception:
        return _heuristic_context(job, base)


def _extract_with_llm(
    *,
    title: str,
    description: str,
    existing_locations: list[str],
    existing_department: str | None,
) -> JobSearchContext:
    model = get_chat_model(ingestion=True)
    system = (
        "Extract job search filters for finding employees to contact about this role. "
        "Return ONLY valid JSON with keys:\n"
        "office_locations (array of strings, US cities/states e.g. 'San Jose, CA' — "
        "include every city explicitly mentioned as a work site; not countries alone),\n"
        "department_name (string or null — org unit e.g. 'Red Team Security', 'Sales Cloud'),\n"
        "department_keywords (array of 2-6 short phrases for matching titles, e.g. "
        "['red team', 'offensive security', 'product security']),\n"
        "team_name (string or null),\n"
        "role_family (string or null — e.g. security, ml, data, platform).\n"
        "Prefer specific office cities over generic 'United States'. "
        "Do not invent locations or departments not supported by the text."
    )
    user = (
        f"Title: {title}\n"
        f"Known locations from ingest: {existing_locations}\n"
        f"Known department from ingest: {existing_department}\n\n"
        f"Description:\n{description[:80_000]}"
    )
    response = model.invoke([SystemMessage(content=system), HumanMessage(content=user)])
    payload = _parse_json(str(response.content))
    return JobSearchContext(
        office_locations=_coerce_str_list(payload.get("office_locations")),
        department_name=_null_str(payload.get("department_name")),
        department_keywords=_coerce_str_list(payload.get("department_keywords")),
        team_name=_null_str(payload.get("team_name")),
        role_family=_null_str(payload.get("role_family")),
    )


def _heuristic_context(job: Job, base: JobSearchContext) -> JobSearchContext:
    text = f"{job.title}\n{job.description or ''}".lower()
    locs = list(base.office_locations)
    for alias, normalized in _CITY_ALIASES.items():
        if alias in text and normalized not in locs:
            locs.append(normalized)
    keywords: list[str] = []
    dept = base.department_name
    for pattern, kw in (
        (r"red team", "red team"),
        (r"product security", "product security"),
        (r"offensive security", "offensive security"),
        (r"\bsecurity\b", "security"),
        (r"machine learning", "machine learning"),
        (r"trust and safety", "trust and safety"),
    ):
        if re.search(pattern, text):
            keywords.append(kw)
    if dept and dept not in keywords:
        keywords.insert(0, dept)
    return JobSearchContext(
        office_locations=locs,
        department_name=dept,
        department_keywords=keywords[:6],
        team_name=base.team_name,
        role_family=base.role_family,
    )


def _parse_json(content: str) -> dict[str, Any]:
    content = content.strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)
    data = json.loads(content)
    if not isinstance(data, dict):
        raise ValueError("Expected JSON object")
    return data


def _coerce_str_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return []


def _null_str(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s or None
