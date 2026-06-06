"""Public ATS job board APIs (Greenhouse, Lever, Ashby)."""

from __future__ import annotations

import re
from html import unescape
from typing import Any

import httpx

from openrole.schemas.job import ParsedJob
from openrole.scrapers.url_detect import JobPlatform, JobUrlInfo

_HTTP_TIMEOUT = 30.0
_HEADERS = {"User-Agent": "OpenRole/0.1 (job research; +https://github.com/NisargaGondi/openrole)"}


def fetch_from_ats(info: JobUrlInfo) -> ParsedJob:
    if info.platform == JobPlatform.GREENHOUSE:
        return _fetch_greenhouse(info)
    if info.platform == JobPlatform.LEVER:
        return _fetch_lever(info)
    if info.platform == JobPlatform.ASHBY:
        return _fetch_ashby(info)
    raise ValueError(f"Unsupported ATS platform: {info.platform}")


def _fetch_greenhouse(info: JobUrlInfo) -> ParsedJob:
    if not info.board_token or not info.job_id:
        raise ValueError(
            "Greenhouse URL must look like boards.greenhouse.io/{company}/jobs/{id}"
        )
    url = (
        f"https://boards-api.greenhouse.io/v1/boards/{info.board_token}"
        f"/jobs/{info.job_id}?questions=true"
    )
    data = _get_json(url)
    departments = data.get("departments") or []
    department = departments[0]["name"] if departments else None
    location = data.get("location") or {}
    loc_name = location.get("name") if isinstance(location, dict) else str(location)
    locations = [loc_name] if loc_name else []
    company_name = _title_case_board(info.board_token)
    content = data.get("content") or ""
    return ParsedJob(
        title=data.get("title") or "Unknown role",
        company_name=company_name,
        description=_strip_html(content),
        department=department,
        locations=locations,
        company_domain=_guess_domain_from_board(info.board_token),
        source_url=data.get("absolute_url") or info.url,
        source_platform=JobPlatform.GREENHOUSE.value,
        apply_url=data.get("absolute_url") or info.url,
        external_id=str(data.get("id") or info.job_id),
        raw_payload=data,
    )


def _fetch_lever(info: JobUrlInfo) -> ParsedJob:
    if not info.company_slug or not info.job_id:
        raise ValueError("Lever URL must look like jobs.lever.co/{company}/{posting_id}")
    url = f"https://api.lever.co/v0/postings/{info.company_slug}/{info.job_id}"
    data = _get_json(url)
    categories = data.get("categories") or {}
    locations: list[str] = []
    if categories.get("location"):
        locations.append(categories["location"])
    if categories.get("allLocations"):
        locations.extend(categories["allLocations"])
    locations = list(dict.fromkeys(locations))
    description = data.get("description") or data.get("descriptionPlain") or ""
    if isinstance(description, list):
        description = "\n".join(str(x) for x in description)
    return ParsedJob(
        title=data.get("title") or data.get("text") or "Unknown role",
        company_name=_title_case_board(info.company_slug),
        description=_strip_html(str(description)),
        department=categories.get("team") or categories.get("department"),
        locations=locations,
        company_domain=None,
        source_url=data.get("hostedUrl") or info.url,
        source_platform=JobPlatform.LEVER.value,
        apply_url=data.get("applyUrl") or data.get("hostedUrl") or info.url,
        external_id=str(data.get("id") or info.job_id),
        raw_payload=data,
    )


def _fetch_ashby(info: JobUrlInfo) -> ParsedJob:
    if not info.company_slug:
        raise ValueError("Ashby URL must look like jobs.ashbyhq.com/{org}/{job_id}")
    list_url = f"https://api.ashbyhq.com/posting-api/job-board/{info.company_slug}"
    payload = _get_json(list_url)
    jobs = payload.get("jobs") or []
    target = None
    for job in jobs:
        if str(job.get("id")) == info.job_id or job.get("jobUrl") == info.url.rstrip("/"):
            target = job
            break
    if target is None and info.job_id:
        # Ashby public ids in URL are often UUIDs matching `id` field
        for job in jobs:
            if info.job_id in (job.get("jobUrl") or ""):
                target = job
                break
    if target is None:
        raise ValueError(f"Ashby job not found in board '{info.company_slug}'")
    location = target.get("location") or target.get("locationName")
    locations = [location] if location else []
    if target.get("secondaryLocations"):
        locations.extend(target["secondaryLocations"])
    description = target.get("descriptionHtml") or target.get("descriptionPlain") or ""
    return ParsedJob(
        title=target.get("title") or "Unknown role",
        company_name=target.get("companyName") or _title_case_board(info.company_slug),
        description=_strip_html(str(description)),
        department=target.get("department") or target.get("team"),
        locations=list(dict.fromkeys(locations)),
        company_domain=None,
        source_url=target.get("jobUrl") or info.url,
        source_platform=JobPlatform.ASHBY.value,
        apply_url=target.get("applyUrl") or target.get("jobUrl") or info.url,
        external_id=str(target.get("id") or info.job_id),
        raw_payload=target,
    )


def _get_json(url: str) -> dict[str, Any]:
    with httpx.Client(timeout=_HTTP_TIMEOUT, headers=_HEADERS, follow_redirects=True) as client:
        response = client.get(url)
        response.raise_for_status()
        data = response.json()
    if not isinstance(data, dict):
        raise ValueError(f"Unexpected JSON from {url}")
    return data


def _strip_html(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html)
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _title_case_board(slug: str) -> str:
    return slug.replace("-", " ").replace("_", " ").title()


def _guess_domain_from_board(token: str) -> str | None:
    if "." in token:
        return token.lower()
    return None
