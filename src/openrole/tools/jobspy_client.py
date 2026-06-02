"""JobSpy wrapper for LinkedIn / Indeed search-based ingestion."""

from __future__ import annotations

import re
from typing import Any

from openrole.schemas.job import ParsedJob
from openrole.scrapers.url_detect import JobPlatform


def fetch_linkedin_by_search(
    *,
    company: str | None = None,
    title: str | None = None,
    location: str | None = None,
    linkedin_job_id: str | None = None,
    source_url: str | None = None,
) -> ParsedJob:
    """Find a LinkedIn posting via JobSpy search (no direct URL API)."""
    from jobspy import scrape_jobs

    search_term = " ".join(p for p in [title, company] if p) or "software engineer"
    df = scrape_jobs(
        site_name=["linkedin"],
        search_term=search_term,
        location=location or "",
        results_wanted=30,
        linkedin_fetch_description=True,
    )
    if df is None or df.empty:
        raise ValueError("No LinkedIn jobs returned from JobSpy for this search")

    row = None
    if linkedin_job_id:
        id_col = "id" if "id" in df.columns else None
        link_col = "job_url" if "job_url" in df.columns else "link"
        for _, candidate in df.iterrows():
            link = str(candidate.get(link_col, ""))
            if linkedin_job_id in link or (
                id_col and str(candidate.get(id_col, "")) == linkedin_job_id
            ):
                row = candidate
                break
    if row is None:
        row = df.iloc[0]

    return _row_to_parsed_job(row, source_url=source_url or str(row.get("job_url", "")))


def fetch_indeed_by_search(
    *,
    company: str | None = None,
    title: str | None = None,
    location: str | None = None,
    indeed_job_id: str | None = None,
    source_url: str | None = None,
) -> ParsedJob:
    from jobspy import scrape_jobs

    search_term = " ".join(p for p in [title, company] if p) or "software engineer"
    df = scrape_jobs(
        site_name=["indeed"],
        search_term=search_term,
        location=location or "United States",
        results_wanted=30,
        country_indeed="USA",
    )
    if df is None or df.empty:
        raise ValueError("No Indeed jobs returned from JobSpy for this search")

    row = None
    if indeed_job_id:
        for _, candidate in df.iterrows():
            link = str(candidate.get("job_url", ""))
            if indeed_job_id in link:
                row = candidate
                break
    if row is None:
        row = df.iloc[0]

    return _row_to_parsed_job(
        row,
        source_url=source_url or str(row.get("job_url", "")),
        platform=JobPlatform.INDEED.value,
    )


def _row_to_parsed_job(row: Any, *, source_url: str, platform: str = "linkedin") -> ParsedJob:
    title = str(row.get("title") or "Unknown role")
    company = str(row.get("company") or row.get("company_name") or "Unknown company")
    description = row.get("description")
    if description is not None and str(description) == "nan":
        description = None
    location = row.get("location")
    locations = [str(location)] if location and str(location) != "nan" else []
    return ParsedJob(
        title=title,
        company_name=company,
        description=str(description) if description else None,
        department=None,
        locations=locations,
        company_domain=_domain_from_company(company),
        source_url=source_url or None,
        source_platform=platform,
        apply_url=source_url or None,
        external_id=_extract_id_from_url(source_url),
        raw_payload={k: (None if str(v) == "nan" else v) for k, v in dict(row).items()},
    )


def _domain_from_company(company: str) -> str | None:
    slug = re.sub(r"[^a-z0-9]+", "", company.lower())
    if len(slug) < 3:
        return None
    return f"{slug}.com"


def _extract_id_from_url(url: str) -> str | None:
    match = re.search(r"/jobs/view/(\d+)", url)
    return match.group(1) if match else None
