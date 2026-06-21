"""Apollo.io client for organization enrich and people search."""

from __future__ import annotations

import re
from typing import Any

import httpx

from openrole.config import get_settings

BASE_URL = "https://api.apollo.io/api/v1"
_HEADERS = {"Content-Type": "application/json", "Cache-Control": "no-cache"}


class ApolloError(RuntimeError):
    pass


class ApolloNotConfiguredError(ApolloError):
    pass


def is_configured() -> bool:
    settings = get_settings()
    return bool(settings.apollo_enabled and settings.apollo_api_key)


def _api_key() -> str:
    key = get_settings().apollo_api_key
    if not key:
        raise ApolloNotConfiguredError("APOLLO_API_KEY is not set in .env")
    return key


def _request(method: str, path: str, *, json_body: dict[str, Any] | None = None) -> dict[str, Any]:
    headers = {**_HEADERS, "X-Api-Key": _api_key()}
    url = f"{BASE_URL}{path}"
    with httpx.Client(timeout=45.0, headers=headers) as client:
        response = client.request(method, url, json=json_body or {})
    if response.status_code == 401:
        raise ApolloError("Apollo API key rejected (401). Check APOLLO_API_KEY.")
    if response.status_code == 403:
        raise ApolloError(
            "Apollo API forbidden (403). People search requires a master API key on your plan."
        )
    if response.status_code == 429:
        raise ApolloError("Apollo rate limit hit (429). Retry in a few minutes.")
    if response.status_code >= 400:
        raise ApolloError(f"Apollo HTTP {response.status_code}: {response.text[:300]}")
    data = response.json()
    return data if isinstance(data, dict) else {"raw": data}


def enrich_organization(*, domain: str) -> dict[str, Any]:
    """Resolve org metadata and Apollo organization id from domain."""
    clean = _normalize_domain(domain)
    data = _request("POST", "/organizations/enrich", json_body={"domain": clean})
    org = data.get("organization") or {}
    return org if isinstance(org, dict) else {}


def search_organization(*, company_name: str) -> dict[str, Any]:
    """Find organization by name; returns best match org dict or {}."""
    data = _request(
        "POST",
        "/mixed_companies/search",
        json_body={
            "q_organization_name": company_name,
            "page": 1,
            "per_page": 5,
        },
    )
    for key in ("organizations", "accounts"):
        rows = data.get(key) or []
        if not isinstance(rows, list):
            continue
        name_l = company_name.lower()
        for row in rows:
            if not isinstance(row, dict):
                continue
            org_name = str(row.get("name") or "").lower()
            if name_l in org_name or org_name in name_l:
                return row
        if rows and isinstance(rows[0], dict):
            return rows[0]
    return {}


def search_people(
    *,
    domain: str,
    person_titles: list[str] | None = None,
    person_seniorities: list[str] | None = None,
    person_locations: list[str] | None = None,
    q_keywords: str | None = None,
    per_page: int = 25,
    page: int = 1,
) -> list[dict[str, Any]]:
    """People API Search (no emails; use match_person to enrich)."""
    clean = _normalize_domain(domain)
    body: dict[str, Any] = {
        "q_organization_domains_list": [clean],
        "page": page,
        "per_page": min(per_page, 100),
    }
    if person_titles:
        body["person_titles"] = person_titles
    if person_seniorities:
        body["person_seniorities"] = person_seniorities
    if person_locations:
        body["person_locations"] = person_locations
    if q_keywords:
        body["q_keywords"] = q_keywords

    data = _request("POST", "/mixed_people/api_search", json_body=body)
    people = data.get("people") or []
    return [p for p in people if isinstance(p, dict)]


def match_person(*, apollo_id: str) -> dict[str, Any]:
    """Enrich one person (uses Apollo credits). Returns full person object."""
    data = _request("POST", "/people/match", json_body={"id": apollo_id})
    person = data.get("person") or {}
    return person if isinstance(person, dict) else {}


def find_person_by_name(
    *,
    domain: str,
    full_name: str,
    title: str | None = None,
) -> dict[str, Any] | None:
    """Search Apollo for a person at domain; return best name match or None."""
    clean = _normalize_domain(domain)
    if not clean or not full_name.strip():
        return None

    search_name = _normalize_name_for_match(full_name)
    candidates = search_people(
        domain=clean,
        q_keywords=full_name.strip(),
        per_page=15,
    )
    if not candidates:
        candidates = search_people(domain=clean, per_page=25)

    best: dict[str, Any] | None = None
    best_score = 0.0
    for person in candidates:
        score = _name_match_score(search_name, _person_display_name(person))
        if title and person.get("title"):
            title_l = title.lower()
            person_title = str(person.get("title")).lower()
            if any(tok in person_title for tok in title_l.split() if len(tok) > 3):
                score += 0.15
        if score > best_score:
            best_score = score
            best = person

    if best is None or best_score < 0.55:
        return None
    return best


def _normalize_name_for_match(name: str) -> str:
    cleaned = re.sub(r"\*+", "", name.lower())
    cleaned = re.sub(r"[^a-z\s]", " ", cleaned)
    return " ".join(cleaned.split())


def _name_match_score(left: str, right: str) -> float:
    l_parts = left.split()
    r_parts = _normalize_name_for_match(right).split()
    if not l_parts or not r_parts:
        return 0.0
    if left == _normalize_name_for_match(right):
        return 1.0
    if l_parts[0] == r_parts[0] and l_parts[-1][:3] == r_parts[-1][:3]:
        return 0.85
    if l_parts[0] == r_parts[0]:
        return 0.6
    return 0.0


def probe_apollo(*, domain: str = "google.com") -> dict[str, Any]:
    """Connectivity test for Settings diagnostics."""
    if not is_configured():
        return {"ok": False, "error": "APOLLO_API_KEY not set"}
    try:
        people = search_people(domain=domain, person_titles=["engineer"], per_page=2)
        sample = None
        if people:
            row = people[0]
            sample = {
                "name": _person_display_name(row),
                "title": row.get("title"),
                "has_email": row.get("has_email"),
            }
        return {"ok": True, "count": len(people), "domain": domain, "sample": sample}
    except ApolloError as exc:
        return {"ok": False, "error": str(exc)}


def normalize_domain(domain: str) -> str:
    return _normalize_domain(domain)


def _normalize_domain(domain: str) -> str:
    d = domain.strip().lower()
    for prefix in ("https://", "http://", "www."):
        if d.startswith(prefix):
            d = d[len(prefix) :]
    return d.split("/")[0].lstrip("@")


def _person_display_name(person: dict[str, Any]) -> str:
    first = (person.get("first_name") or "").strip()
    last = (person.get("last_name") or person.get("last_name_obfuscated") or "").strip()
    name = (person.get("name") or f"{first} {last}").strip()
    return name or "Unknown"


def person_to_fields(person: dict[str, Any]) -> dict[str, Any]:
    """Normalize Apollo person dict to common OpenRole fields."""
    loc_parts = [
        person.get("city"),
        person.get("state"),
        person.get("country"),
    ]
    location = ", ".join(p for p in loc_parts if p) or None
    org = person.get("organization") or {}
    return {
        "full_name": _person_display_name(person),
        "title": person.get("title"),
        "email": person.get("email"),
        "linkedin_url": person.get("linkedin_url"),
        "location": location,
        "apollo_person_id": person.get("id"),
        "has_email": person.get("has_email"),
        "organization_name": org.get("name") if isinstance(org, dict) else None,
        "raw": person,
    }


def person_to_research_facts(person: dict[str, Any]) -> dict[str, Any]:
    """Extract structured career/public facts from an Apollo person for research synthesis."""
    org = person.get("organization") if isinstance(person.get("organization"), dict) else {}
    employment: list[dict[str, Any]] = []
    for row in person.get("employment_history") or []:
        if not isinstance(row, dict):
            continue
        org_row = row.get("organization")
        company_name = None
        if isinstance(org_row, dict):
            company_name = org_row.get("name")
        elif isinstance(org_row, str):
            company_name = org_row
        employment.append(
            {
                "title": row.get("title"),
                "company": company_name or row.get("organization_name"),
                "start_date": row.get("start_date"),
                "end_date": row.get("end_date"),
                "current": row.get("current"),
            }
        )

    loc_parts = [person.get("city"), person.get("state"), person.get("country")]
    return {
        "full_name": _person_display_name(person),
        "headline": person.get("headline"),
        "title": person.get("title"),
        "seniority": person.get("seniority"),
        "departments": person.get("departments") or [],
        "functions": person.get("functions") or [],
        "employment_history": employment[:6],
        "organization": {
            "name": org.get("name"),
            "industry": org.get("industry"),
            "estimated_num_employees": org.get("estimated_num_employees"),
        },
        "location": ", ".join(p for p in loc_parts if p) or None,
        "linkedin_url": person.get("linkedin_url"),
        "github_url": person.get("github_url"),
        "twitter_url": person.get("twitter_url"),
        "email": person.get("email"),
    }
