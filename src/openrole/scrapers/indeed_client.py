"""Direct Indeed viewjob fetch by job key (jk=…)."""

from __future__ import annotations

import json
import re
from html import unescape
from typing import Any
from urllib.parse import urlparse

import httpx

from openrole.schemas.job import ParsedJob
from openrole.scrapers.url_detect import JobPlatform
from openrole.util.json_safe import json_safe_dict

_INDEED_MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6_1 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 Indeed App 193.1"
)


class IndeedFetchError(Exception):
    pass


def fetch_indeed_by_job_key(
    job_key: str,
    *,
    source_url: str | None = None,
) -> ParsedJob:
    """Fetch a single Indeed posting by its jk id (mobile viewjob + JSON-LD)."""
    job_key = (job_key or "").strip()
    if not job_key:
        raise IndeedFetchError("Missing Indeed job key (jk=…)")

    canonical_url = source_url or f"https://www.indeed.com/viewjob?jk={job_key}"
    mobile_url = f"https://www.indeed.com/m/viewjob?jk={job_key}"

    html = _fetch_html(mobile_url)
    if job_key not in html:
        raise IndeedFetchError(
            f"Indeed page did not contain job key {job_key} (blocked or expired listing)."
        )

    posting = _parse_job_posting_json_ld(html)
    if posting is None:
        posting = _parse_initial_data(html, job_key)
    if posting is None:
        raise IndeedFetchError(
            f"Could not parse Indeed job {job_key} from the mobile viewjob page."
        )

    title = str(posting.get("title") or "Unknown role")
    company = _company_name(posting)
    description = posting.get("description")
    if description is not None:
        description = str(description)

    locations = _locations_from_posting(posting)
    return ParsedJob(
        title=title,
        company_name=company or "Unknown company",
        description=description,
        department=None,
        locations=locations,
        company_domain=None,
        source_url=canonical_url,
        source_platform=JobPlatform.INDEED.value,
        apply_url=canonical_url,
        external_id=job_key,
        raw_payload=json_safe_dict(
            {
                "indeed_fetch": "mobile_viewjob",
                "job_key": job_key,
                "mobile_url": mobile_url,
                "json_ld": posting,
            }
        ),
    )


def _fetch_html(url: str) -> str:
    try:
        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
            response = client.get(url, headers={"User-Agent": _INDEED_MOBILE_UA})
            response.raise_for_status()
            return response.text[:800_000]
    except httpx.HTTPError as exc:
        raise IndeedFetchError(f"Indeed HTTP fetch failed for {url}: {exc}") from exc


def _parse_job_posting_json_ld(html: str) -> dict[str, Any] | None:
    for match in re.finditer(
        r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>',
        html,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        try:
            data = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if isinstance(item, dict) and item.get("@type") == "JobPosting":
                return item
    return None


def _parse_initial_data(html: str, job_key: str) -> dict[str, Any] | None:
    match = re.search(r"window\._initialData\s*=\s*(\{.*?\})\s*;", html, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None

    blob = json.dumps(data)
    if job_key not in blob:
        return None

    title = _deep_find(data, "title")
    description = _deep_find(data, "description")
    if isinstance(description, dict):
        description = description.get("html") or description.get("text")
    company = _deep_find(data, "sourceEmployerName") or _deep_find(data, "companyName")
    location = _deep_find(data, "formatted", parent_key="location")
    if isinstance(location, dict):
        location = location.get("short") or location.get("long")

    if not title and not description:
        return None
    return {
        "title": title,
        "description": description,
        "hiringOrganization": {"name": company} if company else {},
        "jobLocation": location,
    }


def _deep_find(obj: Any, key: str, *, parent_key: str | None = None) -> Any:
    if isinstance(obj, dict):
        if parent_key and key in obj:
            return obj[key]
        for k, v in obj.items():
            if k == key and parent_key is None:
                return v
            found = _deep_find(v, key, parent_key=parent_key)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = _deep_find(item, key, parent_key=parent_key)
            if found is not None:
                return found
    return None


def _company_name(posting: dict[str, Any]) -> str | None:
    org = posting.get("hiringOrganization")
    if isinstance(org, dict):
        name = org.get("name")
        return str(name) if name else None
    if isinstance(org, str):
        return org
    return None


def _locations_from_posting(posting: dict[str, Any]) -> list[str]:
    loc = posting.get("jobLocation")
    if isinstance(loc, str) and loc.strip():
        return [loc.strip()]
    if isinstance(loc, dict):
        address = loc.get("address")
        if isinstance(address, dict):
            parts = [
                address.get("addressLocality"),
                address.get("addressRegion"),
            ]
            label = ", ".join(str(p) for p in parts if p)
            if label:
                return [label]
        name = loc.get("name")
        if name:
            return [str(name)]
    if isinstance(loc, list) and loc:
        out: list[str] = []
        for item in loc:
            if isinstance(item, str) and item.strip():
                out.append(item.strip())
            elif isinstance(item, dict):
                address = item.get("address")
                if isinstance(address, dict):
                    parts = [address.get("addressLocality"), address.get("addressRegion")]
                    label = ", ".join(str(p) for p in parts if p)
                    if label:
                        out.append(label)
        if out:
            return out
    return []


def indeed_job_key_from_url(url: str) -> str | None:
    parsed = urlparse(url)
    if "indeed.com" not in (parsed.netloc or "").lower():
        return None
    match = re.search(r"[?&]jk=([a-f0-9]+)", url, re.IGNORECASE)
    return match.group(1) if match else None
