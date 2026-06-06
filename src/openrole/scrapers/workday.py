"""Workday job postings via the public CXS JSON API (no browser required)."""

from __future__ import annotations

import re
from html import unescape
from typing import Any
from urllib.parse import urlparse

import httpx

from openrole.schemas.job import ParsedJob
from openrole.scrapers.url_detect import JobUrlInfo

_HEADERS = {
    "User-Agent": "OpenRole/0.1 (job research)",
    "Accept": "application/json",
}


class WorkdayParseError(ValueError):
    pass


def fetch_from_workday(info: JobUrlInfo) -> ParsedJob:
    host, tenant, site, job_path = _parse_workday_url(info.url)
    api_url = f"https://{host}/wday/cxs/{tenant}/{site}/{job_path}"
    with httpx.Client(timeout=30.0, headers=_HEADERS, follow_redirects=True) as client:
        response = client.get(api_url)
        if response.status_code == 404:
            raise WorkdayParseError(
                "Workday job not found. Check the URL or try a full /job/... link from the posting."
            )
        response.raise_for_status()
        data = response.json()

    posting = data.get("jobPostingInfo") or {}
    org = data.get("hiringOrganization") or {}
    if not posting:
        raise WorkdayParseError("Workday response did not include jobPostingInfo")

    description_html = posting.get("jobDescription") or ""
    location = posting.get("location") or posting.get("jobRequisitionLocation")
    locations = [str(location)] if location else []

    return ParsedJob(
        title=posting.get("title") or "Unknown role",
        company_name=org.get("name") or _title_from_tenant(tenant),
        description=_strip_html(str(description_html)),
        department=None,
        locations=locations,
        company_domain=_domain_from_tenant(tenant),
        source_url=posting.get("externalUrl") or info.url,
        source_platform="workday",
        apply_url=posting.get("externalUrl") or info.url,
        external_id=str(posting.get("jobPostingId") or posting.get("jobReqId") or ""),
        raw_payload={"jobPostingInfo": posting, "hiringOrganization": org},
    )


def _parse_workday_url(url: str) -> tuple[str, str, str, str]:
    parsed = urlparse(url.strip())
    host = parsed.netloc.lower()
    if "myworkdayjobs.com" not in host:
        raise WorkdayParseError("Not a Workday careers URL")

    tenant = host.split(".")[0]
    parts = [segment for segment in parsed.path.split("/") if segment]
    if parts and re.match(r"^[a-z]{2}-[A-Z]{2}$", parts[0]):
        parts = parts[1:]

    if "job" not in parts:
        raise WorkdayParseError(
            "Workday URL must include /job/{location}/{slug} — open the job posting, not the board home page."
        )

    job_index = parts.index("job")
    site = parts[0] if job_index >= 1 else tenant
    job_path = "/".join(parts[job_index:])
    return host, tenant, site, job_path


def _strip_html(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", unescape(text)).strip()


def _title_from_tenant(tenant: str) -> str:
    return tenant.replace("-", " ").title()


def _domain_from_tenant(tenant: str) -> str | None:
    if tenant in ("wd1", "wd3", "wd5", "wd10"):
        return None
    return f"{tenant}.com"
