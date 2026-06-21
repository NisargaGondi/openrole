"""Discover people via Tavily web search (LinkedIn public profiles).

Query templates (no LLM — sent directly to Tavily Search API):

  company_wide:
    "{company}" site:linkedin.com/in

  department:
    "{department_terms}" "{company}" site:linkedin.com/in

  department_location:
    "{department_term}" "{company}" "{city_or_region}" site:linkedin.com/in

  role_title:
    "{company}" "{short_job_title}" engineer site:linkedin.com/in

  alumni (optional):
    "{company}" "Carnegie Mellon" site:linkedin.com/in

Each query runs with search_depth=basic first. If a query returns fewer than
MIN_PROFILES_PER_QUERY LinkedIn profiles, the same query is retried with
search_depth=advanced.
"""

from __future__ import annotations

import re
from typing import Any

from openrole.config import get_settings
from openrole.db.models import Job
from openrole.schemas.job_context import JobSearchContext
from openrole.scrapers.location_match import JobLocationTarget
from openrole.tools.web_search import is_configured, search_web

_LINKEDIN_RE = re.compile(r"https?://(?:[\w.-]+\.)?linkedin\.com/in/[\w\-_%]+", re.I)
_MIN_PROFILES_PER_QUERY = 2
_MAX_RESULTS_PER_QUERY = 8

# Documented templates for Settings / debugging (placeholders in braces).
TAVILY_QUERY_TEMPLATES: dict[str, str] = {
    "company_wide": '{company} site:linkedin.com/in',
    "department": '"{department_terms}" "{company}" site:linkedin.com/in',
    "department_location": '"{department_term}" "{company}" "{location}" site:linkedin.com/in',
    "role_title": '"{company}" "{role_title}" engineer site:linkedin.com/in',
    "alumni": '"{company}" "{school_name}" site:linkedin.com/in',
}


def discover_people_via_tavily(
    *,
    company_name: str,
    job: Job,
    search_context: JobSearchContext,
    location_target: JobLocationTarget,
    on_progress: Any = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Run multi-pass Tavily LinkedIn discovery; returns Apollo-shaped person dicts."""
    warnings: list[str] = []
    if not is_configured():
        warnings.append("Tavily not configured — set TAVILY_API_KEY for LinkedIn people discovery.")
        return [], warnings

    search_company = normalize_company_search_name(company_name)
    specs = build_tavily_query_specs(
        company=search_company,
        job=job,
        search_context=search_context,
        location_target=location_target,
    )
    if not specs:
        warnings.append("Tavily: no queries built (missing company/department context).")
        return [], warnings

    seen_linkedin: set[str] = set()
    merged: list[dict[str, Any]] = []

    for spec in specs:
        qtype = spec["query_type"]
        query = spec["query"]
        if on_progress:
            on_progress(f"Tavily [{qtype}]: searching…")
        profiles = _search_query(query, query_type=qtype)
        if len(profiles) < _MIN_PROFILES_PER_QUERY:
            if on_progress:
                on_progress(f"Tavily [{qtype}]: retry with advanced depth")
            advanced = _search_query(query, query_type=qtype, search_depth="advanced")
            profiles = _merge_profile_lists(profiles, advanced)

        new_count = 0
        for profile in profiles:
            key = profile["linkedin_url"].lower().rstrip("/")
            if key in seen_linkedin:
                continue
            seen_linkedin.add(key)
            person = _to_ranking_person(profile, company=search_company, spec=spec)
            merged.append(person)
            new_count += 1

        if on_progress:
            on_progress(f"Tavily [{qtype}]: +{new_count} profile(s)")
        warnings.append(
            f"Tavily [{qtype}]: +{new_count} profiles — `{query[:90]}{'…' if len(query) > 90 else ''}`"
        )

    if merged:
        warnings.append(f"Tavily total: {len(merged)} unique LinkedIn profiles for {search_company}.")
    else:
        warnings.append(f"Tavily: no LinkedIn profiles found for {search_company}.")

    return merged, warnings


def build_tavily_query_specs(
    *,
    company: str,
    job: Job,
    search_context: JobSearchContext,
    location_target: JobLocationTarget,
) -> list[dict[str, str]]:
    """Build ordered Tavily search specs (broad → narrow)."""
    specs: list[dict[str, str]] = []
    seen_queries: set[str] = set()

    def add(query_type: str, query: str) -> None:
        q = " ".join(query.split())
        if not q or q.lower() in seen_queries:
            return
        seen_queries.add(q.lower())
        specs.append({"query_type": query_type, "query": q})

    add("company_wide", TAVILY_QUERY_TEMPLATES["company_wide"].format(company=company))

    dept_terms = search_context.expanded_department_queries()
    if dept_terms:
        # Use first two distinct dept tokens — avoid "Artificial Intelligence Artificial".
        unique: list[str] = []
        for term in dept_terms:
            if term.lower() not in {u.lower() for u in unique}:
                unique.append(term)
        dept_blob = " ".join(unique[:2])
        add(
            "department",
            TAVILY_QUERY_TEMPLATES["department"].format(
                department_terms=dept_blob,
                company=company,
            ),
        )
        for term in unique[:3]:
            for loc in _location_phrases(search_context, location_target)[:2]:
                add(
                    "department_location",
                    TAVILY_QUERY_TEMPLATES["department_location"].format(
                        department_term=term,
                        company=company,
                        location=loc,
                    ),
                )

    role_short = _short_role_title(job.title or "")
    if role_short:
        add(
            "role_title",
            TAVILY_QUERY_TEMPLATES["role_title"].format(
                company=company,
                role_title=role_short,
            ),
        )

    settings = get_settings()
    if settings.cmu_school_name:
        add(
            "alumni",
            TAVILY_QUERY_TEMPLATES["alumni"].format(
                company=company,
                school_name=settings.cmu_school_name,
            ),
        )

    return specs


def normalize_company_search_name(company_name: str) -> str:
    """Short brand name for web search (not legal entity names)."""
    lower = company_name.strip().lower()
    if "amazon" in lower:
        return "Amazon"
    if "meta" in lower or "facebook" in lower:
        return "Meta"
    if "anthropic" in lower:
        return "Anthropic"
    if "milwaukee tool" in lower or "milwaukee" in lower:
        return "Milwaukee Tool"
    if "d. e. shaw" in lower or "d.e. shaw" in lower or "deshaw" in lower:
        return "D. E. Shaw Research"
    if "google" in lower:
        return "Google"
    if "microsoft" in lower:
        return "Microsoft"
    cleaned = re.sub(r"\b(llc|inc|corp|corporation|ltd|co\.)\b\.?", "", company_name, flags=re.I)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,")
    return cleaned or company_name.strip()


def list_query_templates_for_job(
    *,
    company_name: str,
    job: Job,
    search_context: JobSearchContext,
    location_target: JobLocationTarget,
) -> list[dict[str, str]]:
    """Expose planned queries for UI / debugging."""
    company = normalize_company_search_name(company_name)
    return build_tavily_query_specs(
        company=company,
        job=job,
        search_context=search_context,
        location_target=location_target,
    )


def _location_phrases(
    search_context: JobSearchContext,
    location_target: JobLocationTarget,
) -> list[str]:
    out: list[str] = []
    for loc in search_context.office_locations or []:
        city = loc.split(",")[0].strip()
        if city and city.lower() not in {x.lower() for x in out}:
            out.append(city)
    for token in location_target.city_tokens or ():
        label = token.replace("-", " ").title()
        if label.lower() not in {x.lower() for x in out}:
            out.append(label)
    return out


def _short_role_title(title: str) -> str:
    t = title.strip()
    if not t:
        return ""
    if "," in t:
        t = t.split(",", 1)[0].strip()
    for prefix in ("Senior ", "Staff ", "Principal ", "Lead "):
        if t.startswith(prefix):
            t = t[len(prefix) :]
    return t[:60]


def _search_query(
    query: str,
    *,
    query_type: str,
    search_depth: str = "basic",
) -> list[dict[str, Any]]:
    rows = search_web(query, max_results=_MAX_RESULTS_PER_QUERY, search_depth=search_depth)
    return _parse_linkedin_profiles(rows, query_type=query_type, query=query)


def _merge_profile_lists(a: list[dict], b: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for profile in [*a, *b]:
        key = profile["linkedin_url"].lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(profile)
    return out


def _parse_linkedin_profiles(
    rows: list[dict[str, Any]],
    *,
    query_type: str,
    query: str,
) -> list[dict[str, Any]]:
    profiles: list[dict[str, Any]] = []
    seen: set[str] = set()

    for row in rows:
        if row.get("title") == "summary":
            continue
        url = str(row.get("url") or "")
        title = str(row.get("title") or "")
        content = str(row.get("content") or "")
        blob = f"{title} {content} {url}"

        match = _LINKEDIN_RE.search(blob)
        if not match and "linkedin.com/in/" not in url.lower():
            continue
        linkedin_url = (match.group(0) if match else url).split("?")[0].rstrip("/")

        key = linkedin_url.lower()
        if key in seen:
            continue
        seen.add(key)

        name = _parse_name(title, linkedin_url)
        if not name or not _looks_like_person_name(name):
            continue

        profiles.append(
            {
                "full_name": name,
                "title": _parse_title_from_result(title, name),
                "location": _parse_location(content),
                "linkedin_url": linkedin_url,
                "snippet": content[:240],
                "tavily_score": row.get("score"),
                "tavily_query": query,
                "tavily_query_type": query_type,
            }
        )
    return profiles


def _to_ranking_person(
    profile: dict[str, Any],
    *,
    company: str,
    spec: dict[str, str],
) -> dict[str, Any]:
    full = profile["full_name"]
    first, last = _split_name(full)
    slug = profile["linkedin_url"].rstrip("/").split("/in/")[-1][:80]
    return {
        "id": f"tv:{slug}",
        "first_name": first,
        "last_name": last,
        "name": full,
        "title": profile.get("title"),
        "email": None,
        "linkedin_url": profile["linkedin_url"],
        "location": profile.get("location"),
        "company": company,
        "has_email": False,
        "_openrole_tavily": True,
        "tavily_query": spec.get("query") or profile.get("tavily_query"),
        "tavily_query_type": spec.get("query_type") or profile.get("tavily_query_type"),
        "tavily_score": profile.get("tavily_score"),
        "tavily_snippet": profile.get("snippet"),
    }


def _parse_name(title: str, linkedin_url: str) -> str | None:
    t = title.replace("| LinkedIn", "").strip()
    if " - " in t:
        candidate = t.split(" - ", 1)[0].strip()
        if _looks_like_person_name(candidate):
            return candidate
    if "|" in t:
        candidate = t.split("|", 1)[0].strip()
        if _looks_like_person_name(candidate):
            return candidate
    slug = linkedin_url.rstrip("/").split("/in/")[-1]
    slug = re.sub(r"[\d]+$", "", slug)
    parts = [p for p in re.split(r"[-_]", slug) if p and not p.isdigit()]
    if len(parts) >= 2:
        return f"{parts[0].title()} {' '.join(p.title() for p in parts[1:2])}"
    return t[:80] if _looks_like_person_name(t) else None


def _parse_title_from_result(title: str, name: str) -> str | None:
    t = title.replace("| LinkedIn", "").strip()
    name_l = name.lower()
    if " - " in t:
        left, right = t.split(" - ", 1)
        if name_l in left.lower():
            return right.strip() or None
        return t
    if "|" in t:
        parts = [p.strip() for p in t.split("|")]
        for part in parts:
            if name_l not in part.lower() and len(part) > 3:
                return part
    return None


def _parse_location(content: str) -> str | None:
    for line in content.splitlines():
        line = line.strip()
        if re.search(r",\s*[A-Z]{2}\b", line) or "United States" in line:
            if len(line) < 120:
                return line
    m = re.search(
        r"([A-Za-z .'-]+,\s*[A-Za-z .'-]+(?:,\s*United States)?)",
        content,
    )
    return m.group(1).strip() if m else None


def _looks_like_person_name(text: str) -> bool:
    t = text.strip()
    if not t or len(t) > 80 or "@" in t:
        return False
    lower = t.lower()
    skip = (
        "linkedin",
        "recommended",
        "search",
        "people also viewed",
        "hiring",
        "meta ai",
    )
    if any(s in lower for s in skip):
        return False
    parts = t.split()
    return len(parts) >= 2 and parts[0][0].isalpha() and parts[-1][0].isalpha()


def _split_name(full: str) -> tuple[str, str]:
    parts = full.split()
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], " ".join(parts[1:])
