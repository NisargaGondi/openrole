"""Discover jobs from company career pages and ATS boards."""

from __future__ import annotations

from typing import Any

import httpx

from openrole.schemas.job import ParsedJob
from openrole.scrapers.ats_apis import list_ashby_jobs, list_greenhouse_jobs, list_lever_jobs
from openrole.scrapers.url_detect import JobPlatform

_HTTP_TIMEOUT = 20.0
_HEADERS = {"User-Agent": "OpenRole/0.1 (job scout)"}


def discover_from_company_metadata(
    *,
    company_name: str,
    domain: str | None,
    metadata: dict[str, Any] | None,
) -> list[ParsedJob]:
    """Pull open roles from Greenhouse/Lever/Ashby tokens or careers URL in company metadata."""
    meta = metadata or {}
    jobs: list[ParsedJob] = []

    gh = meta.get("greenhouse_token") or meta.get("greenhouse_board")
    if gh:
        try:
            for item in list_greenhouse_jobs(str(gh)):
                jobs.append(
                    ParsedJob(
                        title=item["title"],
                        company_name=company_name,
                        description=item.get("content"),
                        locations=item.get("locations") or [],
                        company_domain=domain,
                        source_url=item["url"],
                        source_platform=JobPlatform.GREENHOUSE.value,
                        apply_url=item["url"],
                        external_id=str(item.get("id", "")),
                    )
                )
        except Exception:
            pass

    lever = meta.get("lever_slug") or meta.get("lever_client")
    if lever:
        try:
            for item in list_lever_jobs(str(lever)):
                jobs.append(
                    ParsedJob(
                        title=item["title"],
                        company_name=company_name,
                        description=item.get("description"),
                        locations=item.get("locations") or [],
                        company_domain=domain,
                        source_url=item["url"],
                        source_platform=JobPlatform.LEVER.value,
                        apply_url=item["url"],
                        external_id=str(item.get("id", "")),
                    )
                )
        except Exception:
            pass

    ashby = meta.get("ashby_org") or meta.get("ashby_board")
    if ashby:
        try:
            for item in list_ashby_jobs(str(ashby)):
                jobs.append(
                    ParsedJob(
                        title=item["title"],
                        company_name=company_name,
                        description=item.get("description"),
                        locations=item.get("locations") or [],
                        company_domain=domain,
                        source_url=item["url"],
                        source_platform=JobPlatform.ASHBY.value,
                        apply_url=item["url"],
                        external_id=str(item.get("id", "")),
                    )
                )
        except Exception:
            pass

    careers_url = meta.get("careers_url")
    if careers_url:
        from openrole.tools.web_search import is_configured as tavily_ready

        if tavily_ready():
            from openrole.agents.tavily_job_discovery import discover_company_jobs_via_tavily

            tavily_jobs = discover_company_jobs_via_tavily(
                company_name=company_name,
                domain=domain,
                search_terms=["software engineer", "machine learning engineer"],
                careers_url=str(careers_url),
            )
            jobs.extend(tavily_jobs)
        elif not jobs:
            jobs.extend(_probe_careers_page(company_name, domain, str(careers_url)))
    elif not jobs:
        from openrole.tools.web_search import is_configured as tavily_ready

        if tavily_ready() and domain:
            from openrole.agents.tavily_job_discovery import discover_company_jobs_via_tavily

            jobs.extend(
                discover_company_jobs_via_tavily(
                    company_name=company_name,
                    domain=domain,
                    search_terms=["software engineer", "machine learning engineer"],
                )
            )

    return jobs


def _probe_careers_page(company_name: str, domain: str | None, url: str) -> list[ParsedJob]:
    """Lightweight fetch for custom career pages — full parse deferred to ingest_job."""
    try:
        resp = httpx.get(url, headers=_HEADERS, timeout=_HTTP_TIMEOUT, follow_redirects=True)
        resp.raise_for_status()
    except Exception:
        return []
    # Store as a single discoverable entry; user/scout can re-ingest URL for full JD
    return [
        ParsedJob(
            title=f"Careers page — {company_name}",
            company_name=company_name,
            description=resp.text[:5000] if resp.text else None,
            company_domain=domain,
            source_url=url,
            source_platform="careers_page",
            apply_url=url,
            raw_payload={"scout_note": "custom careers page — re-ingest individual job URLs"},
        )
    ]
