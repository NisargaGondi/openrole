"""Structured metadata from SPA career pages (JSON-LD in initial HTML)."""

from __future__ import annotations

import json
import re
from html import unescape
from typing import Any
from urllib.parse import urlparse

_META_DEPARTMENT_PATTERNS = (
    (re.compile(r"systems\s+machine\s+learning|systems\s+ml", re.I), "Artificial Intelligence"),
    (re.compile(r"machine\s+learning|(?:\bML\b)", re.I), "Artificial Intelligence"),
    (re.compile(r"artificial\s+intelligence|\bAI\b", re.I), "Artificial Intelligence"),
    (re.compile(r"security|cyber", re.I), "Security"),
    (re.compile(r"infrastructure|platform", re.I), "Infrastructure"),
)


def extract_spa_hints(url: str, html: str) -> dict[str, Any] | None:
    """Parse embedded JobPosting JSON-LD when present (Meta, many career sites)."""
    posting = extract_job_posting_json_ld(html)
    if not posting:
        return None

    title = _clean_text(posting.get("title"))
    company = _organization_name(posting.get("hiringOrganization"))
    locations = _locations_from_posting(posting)
    description = _description_from_posting(posting)
    department = _infer_department(title, description, url)

    hints: dict[str, Any] = {
        "source": "json_ld_job_posting",
        "title": title,
        "company_name": company,
        "locations": locations,
        "department": department,
        "employment_type": _clean_text(posting.get("employmentType")),
    }
    if description:
        hints["description"] = description
    return {k: v for k, v in hints.items() if v not in (None, "", [])}


def extract_job_posting_json_ld(html: str) -> dict[str, Any] | None:
    """Find JobPosting object in script tags or unicode-escaped inline JSON."""
    for raw in _json_ld_blobs(html):
        posting = _find_job_posting(raw)
        if posting:
            return posting
    return None


def format_structured_metadata_block(hints: dict[str, Any]) -> str:
    """Human + LLM-readable header prepended to scraped body text."""
    lines = ["=== STRUCTURED PAGE METADATA (authoritative — use for title, locations, department) ==="]
    if hints.get("title"):
        lines.append(f"Title: {hints['title']}")
    if hints.get("company_name"):
        lines.append(f"Company: {hints['company_name']}")
    if hints.get("locations"):
        locs = hints["locations"]
        if isinstance(locs, list):
            lines.append(f"Locations: {' · '.join(str(x) for x in locs)}")
    if hints.get("department"):
        lines.append(f"Department: {hints['department']}")
    if hints.get("employment_type"):
        lines.append(f"Employment type: {hints['employment_type']}")
    lines.append("=== END STRUCTURED METADATA ===")
    return "\n".join(lines)


def _json_ld_blobs(html: str) -> list[Any]:
    blobs: list[Any] = []
    for match in re.finditer(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        parsed = _parse_json_blob(match.group(1))
        if parsed is not None:
            blobs.append(parsed)

    if "JobPosting" in html:
        idx = html.find("JobPosting")
        start = html.rfind("{", 0, idx)
        if start >= 0:
            chunk = html[start : start + 80_000]
            parsed = _parse_json_blob(chunk)
            if parsed is not None:
                blobs.append(parsed)
    return blobs


def _parse_json_blob(text: str) -> Any | None:
    text = text.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    try:
        return json.loads(text.encode("utf-8").decode("unicode_escape"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


def _find_job_posting(data: Any) -> dict[str, Any] | None:
    if isinstance(data, dict):
        type_val = data.get("@type") or data.get("\u0040type")
        if type_val == "JobPosting":
            return _normalize_posting(data)
        graph = data.get("@graph")
        if isinstance(graph, list):
            for item in graph:
                found = _find_job_posting(item)
                if found:
                    return found
    elif isinstance(data, list):
        for item in data:
            found = _find_job_posting(item)
            if found:
                return found
    return None


def _normalize_posting(data: dict[str, Any]) -> dict[str, Any]:
    out = dict(data)
    if "\u0040type" in out and "@type" not in out:
        out["@type"] = out.pop("\u0040type")
    return out


def _organization_name(org: Any) -> str | None:
    if isinstance(org, dict):
        return _clean_text(org.get("name"))
    if isinstance(org, str):
        return _clean_text(org)
    return None


def _locations_from_posting(posting: dict[str, Any]) -> list[str]:
    loc = posting.get("jobLocation")
    out: list[str] = []
    items = loc if isinstance(loc, list) else [loc] if loc else []
    for item in items:
        if isinstance(item, str):
            label = _clean_text(item)
            if label:
                out.append(label)
            continue
        if not isinstance(item, dict):
            continue
        name = _clean_text(item.get("name"))
        if name:
            out.append(name)
            continue
        address = item.get("address")
        if isinstance(address, dict):
            parts = [address.get("addressLocality"), address.get("addressRegion")]
            label = ", ".join(str(p) for p in parts if p)
            if label:
                out.append(label)
    deduped: list[str] = []
    for label in out:
        if label not in deduped:
            deduped.append(label)
    return deduped


def _description_from_posting(posting: dict[str, Any]) -> str | None:
    parts: list[str] = []
    for key in ("description", "responsibilities", "qualifications"):
        val = posting.get(key)
        if not val:
            continue
        text = _html_to_text(str(val))
        if text:
            parts.append(f"{key.replace('_', ' ').title()}:\n{text}")
    if not parts:
        return None
    return "\n\n".join(parts)


def _infer_department(title: str | None, description: str | None, url: str) -> str | None:
    host = urlparse(url).netloc.lower()
    blob = " ".join(filter(None, [title, description]))
    for pattern, dept in _META_DEPARTMENT_PATTERNS:
        if pattern.search(blob):
            return dept
    if "metacareers.com" in host and title and re.search(r"engineer|scientist", title, re.I):
        return "Engineering"
    return None


def _html_to_text(html: str) -> str:
    cleaned = re.sub(r"(?is)<br\s*/?>", "\n", html)
    cleaned = re.sub(r"(?is)</p>", "\n\n", cleaned)
    cleaned = re.sub(r"(?is)<li[^>]*>", "\n• ", cleaned)
    cleaned = re.sub(r"(?is)<[^>]+>", " ", cleaned)
    cleaned = unescape(cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = unescape(str(value)).strip()
    text = re.sub(r"\s+", " ", text)
    return text or None
