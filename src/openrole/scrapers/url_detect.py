"""Detect job board platform from a posting URL."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from urllib.parse import urlparse


class JobPlatform(str, Enum):
    GREENHOUSE = "greenhouse"
    LEVER = "lever"
    ASHBY = "ashby"
    LINKEDIN = "linkedin"
    INDEED = "indeed"
    WORKDAY = "workday"
    HANDSHAKE = "handshake"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class JobUrlInfo:
    platform: JobPlatform
    url: str
    board_token: str | None = None
    job_id: str | None = None
    company_slug: str | None = None


def detect_job_url(url: str) -> JobUrlInfo:
    normalized = url.strip()
    parsed = urlparse(normalized)
    host = (parsed.netloc or "").lower()
    path = parsed.path or ""

    if "greenhouse.io" in host:
        return _parse_greenhouse(normalized, host, path)
    if host.endswith("lever.co") or "jobs.lever.co" in host:
        return _parse_lever(normalized, path)
    if "ashbyhq.com" in host:
        return _parse_ashby(normalized, path)
    if "linkedin.com" in host:
        job_id = _first_group(r"/jobs/view/(\d+)", path) or _first_group(r"currentJobId=(\d+)", normalized)
        return JobUrlInfo(JobPlatform.LINKEDIN, normalized, job_id=job_id)
    if "indeed.com" in host:
        job_id = _first_group(r"jk=([a-f0-9]+)", normalized) or _first_group(r"/viewjob\?jk=([a-f0-9]+)", normalized)
        return JobUrlInfo(JobPlatform.INDEED, normalized, job_id=job_id)
    if "myworkdayjobs.com" in host or "workday.com" in host:
        return JobUrlInfo(JobPlatform.WORKDAY, normalized)
    if "joinhandshake.com" in host:
        job_id = _first_group(r"/jobs/(\d+)", path)
        return JobUrlInfo(JobPlatform.HANDSHAKE, normalized, job_id=job_id)

    return JobUrlInfo(JobPlatform.UNKNOWN, normalized)


def _parse_greenhouse(url: str, host: str, path: str) -> JobUrlInfo:
    # boards.greenhouse.io/{token}/jobs/{id}
    match = re.search(r"/([^/]+)/jobs/(\d+)", path)
    if match:
        return JobUrlInfo(
            JobPlatform.GREENHOUSE,
            url,
            board_token=match.group(1),
            job_id=match.group(2),
        )
    # embed on company site: boards-api token sometimes in query
    job_id = _first_group(r"/jobs/(\d+)", path)
    return JobUrlInfo(JobPlatform.GREENHOUSE, url, job_id=job_id)


def _parse_lever(url: str, path: str) -> JobUrlInfo:
    # jobs.lever.co/{company}/{uuid}
    parts = [p for p in path.split("/") if p]
    if len(parts) >= 2:
        return JobUrlInfo(
            JobPlatform.LEVER,
            url,
            company_slug=parts[0],
            job_id=parts[1],
        )
    return JobUrlInfo(JobPlatform.LEVER, url)


def _parse_ashby(url: str, path: str) -> JobUrlInfo:
    # jobs.ashbyhq.com/{org}/{uuid}
    parts = [p for p in path.split("/") if p]
    if len(parts) >= 2:
        return JobUrlInfo(
            JobPlatform.ASHBY,
            url,
            company_slug=parts[0],
            job_id=parts[1],
        )
    return JobUrlInfo(JobPlatform.ASHBY, url)


def _first_group(pattern: str, text: str) -> str | None:
    match = re.search(pattern, text)
    return match.group(1) if match else None
