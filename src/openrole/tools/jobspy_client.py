"""JobSpy wrapper for LinkedIn / Indeed search-based ingestion."""

from __future__ import annotations

import importlib.util
import re
from typing import Any

from openrole.schemas.job import ParsedJob
from openrole.scrapers.url_detect import JobPlatform


def is_available() -> bool:
    return importlib.util.find_spec("jobspy") is not None


def jobspy_install_hint() -> str:
    return (
        "JobSpy is not installed. From the repo root run:\n"
        "  bash scripts/install_jobspy.sh\n"
        "If pip fails (path with apostrophe), use a clone path without `'` in the folder name."
    )


def fetch_linkedin_by_search(
    *,
    company: str | None = None,
    title: str | None = None,
    location: str | None = None,
    linkedin_job_id: str | None = None,
    source_url: str | None = None,
) -> ParsedJob:
    """Find a LinkedIn posting via JobSpy search (no direct URL API)."""
    if not is_available():
        raise ImportError(jobspy_install_hint())

    from jobspy import scrape_jobs

    search_term = " ".join(p for p in [title, company] if p) or "software engineer"
    df = scrape_jobs(
        site_name=["linkedin"],
        search_term=search_term,
        location=location or "United States",
        results_wanted=40,
        linkedin_fetch_description=True,
    )
    if df is None or df.empty:
        raise ValueError(
            f"No LinkedIn jobs returned for search '{search_term}'. "
            "LinkedIn may be rate-limiting — paste the job description as fallback."
        )

    row = _match_row(
        df,
        job_id=linkedin_job_id,
        source_url=source_url,
        url_columns=("job_url", "job_url_direct", "link"),
    )
    if row is None:
        raise ValueError(
            f"Could not match LinkedIn job id={linkedin_job_id or '?'} in search results. "
            "Paste the full job description below."
        )

    resolved_url = source_url or _first_str(row, "job_url", "job_url_direct", "link")
    return _row_to_parsed_job(row, source_url=resolved_url)


def fetch_indeed_by_search(
    *,
    company: str | None = None,
    title: str | None = None,
    location: str | None = None,
    indeed_job_id: str | None = None,
    source_url: str | None = None,
) -> ParsedJob:
    if not is_available():
        raise ImportError(jobspy_install_hint())

    from jobspy import scrape_jobs

    search_term = " ".join(p for p in [title, company] if p) or "software engineer"
    df = scrape_jobs(
        site_name=["indeed"],
        search_term=search_term,
        location=location or "United States",
        results_wanted=40,
        country_indeed="USA",
    )
    if df is None or df.empty:
        raise ValueError("No Indeed jobs returned from JobSpy for this search")

    row = _match_row(
        df,
        job_id=indeed_job_id,
        source_url=source_url,
        url_columns=("job_url", "job_url_direct"),
    )
    if row is None:
        row = df.iloc[0]

    resolved_url = source_url or _first_str(row, "job_url", "job_url_direct")
    return _row_to_parsed_job(
        row,
        source_url=resolved_url,
        platform=JobPlatform.INDEED.value,
    )


def probe_jobspy(*, site: str = "indeed") -> dict[str, Any]:
    """Quick connectivity test for Streamlit / diagnostics."""
    if not is_available():
        return {"ok": False, "error": jobspy_install_hint()}

    from jobspy import scrape_jobs

    site_name = site if site in ("linkedin", "indeed") else "indeed"
    try:
        kwargs: dict[str, Any] = {
            "site_name": [site_name],
            "search_term": "software engineer",
            "results_wanted": 2,
            "linkedin_fetch_description": False,
        }
        if site_name == "indeed":
            kwargs["location"] = "United States"
            kwargs["country_indeed"] = "USA"
        else:
            kwargs["location"] = "United States"

        df = scrape_jobs(**kwargs)
        count = 0 if df is None else len(df)
        sample = None
        if count:
            row = df.iloc[0]
            sample = {
                "title": _first_str(row, "title"),
                "company": _first_str(row, "company", "company_name"),
                "url": _first_str(row, "job_url", "job_url_direct", "link"),
            }
        return {"ok": count > 0, "site": site_name, "count": count, "sample": sample}
    except Exception as exc:
        return {"ok": False, "site": site_name, "error": str(exc)}


def _match_row(df, *, job_id: str | None, source_url: str | None, url_columns: tuple[str, ...]):
    if job_id:
        for _, candidate in df.iterrows():
            for col in url_columns:
                link = str(candidate.get(col, "") or "")
                if job_id in link:
                    return candidate
            if str(candidate.get("id", "")) == job_id:
                return candidate
    if source_url:
        for _, candidate in df.iterrows():
            for col in url_columns:
                link = str(candidate.get(col, "") or "")
                if link and (link in source_url or source_url in link):
                    return candidate
    return None


def _row_to_parsed_job(row: Any, *, source_url: str, platform: str = "linkedin") -> ParsedJob:
    title = _first_str(row, "title") or "Unknown role"
    company = _first_str(row, "company", "company_name") or "Unknown company"
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
        external_id=_extract_id_from_url(source_url or ""),
        raw_payload={
            k: (None if str(v) == "nan" else v) for k, v in dict(row).items()
        },
    )


def _first_str(row: Any, *keys: str) -> str | None:
    for key in keys:
        val = row.get(key)
        if val is not None and str(val) not in ("", "nan"):
            return str(val)
    return None


def _domain_from_company(company: str) -> str | None:
    slug = re.sub(r"[^a-z0-9]+", "", company.lower())
    if len(slug) < 3:
        return None
    return f"{slug}.com"


def _extract_id_from_url(url: str) -> str | None:
    match = re.search(r"/jobs/view/(\d+)", url)
    return match.group(1) if match else None
