"""Universal job page fetcher — Tavily Extract, then httpx + LLM extraction."""

from __future__ import annotations

import re
from html import unescape
from urllib.parse import urlparse

import httpx

from openrole.schemas.job import ParsedJob
from openrole.scrapers.url_detect import JobPlatform, detect_job_url
from openrole.tools.web_search import extract_url, is_configured as tavily_configured

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}
_FALLBACK_USER_AGENTS = (
    "Mozilla/5.0",
    "facebookexternalhit/1.1",
    (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6_1 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1"
    ),
)
_MIN_TEXT_CHARS = 200
_EXTRACT_QUERY = (
    "job posting title company locations cities department team category "
    "description responsibilities qualifications"
)
_SPA_HOSTS = frozenset(
    {
        "metacareers.com",
        "www.metacareers.com",
        "stripe.com",
        "www.stripe.com",
        "careers.airbnb.com",
    }
)


class UniversalScrapeError(Exception):
    pass


def fetch_from_url(url: str, *, source_platform: str | None = None) -> ParsedJob:
    """Fetch any job URL and extract a ParsedJob via page text + LLM."""
    from openrole.agents.job_ingestion import parse_job_page_text

    info = detect_job_url(url)
    if source_platform:
        platform = source_platform
    elif info.platform != JobPlatform.UNKNOWN:
        platform = info.platform.value
    else:
        platform = "universal"

    text, fetch_source, spa_hints = fetch_page_text(url)
    parsed = parse_job_page_text(
        text,
        source_url=url,
        source_platform=platform,
        spa_hints=spa_hints or None,
    )
    meta = dict(parsed.raw_payload or {})
    meta["universal_fetch"] = {"source": fetch_source, "chars": len(text)}
    if spa_hints:
        meta["spa_hints"] = spa_hints
    parsed.raw_payload = meta
    return parsed


def fetch_page_text(url: str) -> tuple[str, str, dict]:
    """Return (page_text, source, spa_hints) — prefers the richest text we can obtain."""
    candidates: list[tuple[str, str]] = []
    spa_hints: dict = {}
    info = detect_job_url(url)
    is_indeed_viewjob = info.platform == JobPlatform.INDEED and info.job_id
    host = urlparse(url).netloc.lower()
    is_spa_host = any(h in host for h in _SPA_HOSTS)

    if is_indeed_viewjob:
        from openrole.scrapers.indeed_client import IndeedFetchError, fetch_indeed_by_job_key

        try:
            parsed = fetch_indeed_by_job_key(info.job_id or "", source_url=url)
            text = "\n\n".join(
                part
                for part in [
                    parsed.title,
                    parsed.company_name,
                    ", ".join(parsed.locations or []),
                    parsed.description or "",
                ]
                if part
            ).strip()
            if len(text) >= _MIN_TEXT_CHARS:
                return text[:120_000], "indeed_mobile_viewjob", spa_hints
        except IndeedFetchError:
            pass

    html_for_hints: str | None = None
    try:
        html_for_hints = _fetch_html(url)
        from openrole.scrapers.spa_hints import extract_spa_hints

        extracted = extract_spa_hints(url, html_for_hints)
        if extracted:
            spa_hints = extracted
            body = str(extracted.get("description") or "")
            if body and len(body) >= _MIN_TEXT_CHARS:
                candidates.append((body, "json_ld"))
        text = _html_to_text(html_for_hints)
        if len(text.strip()) >= _MIN_TEXT_CHARS:
            candidates.append((text, "httpx"))
    except UniversalScrapeError:
        html_for_hints = None

    if tavily_configured():
        for depth in ("basic", "advanced"):
            extracted = extract_url(url, extract_depth=depth, query=_EXTRACT_QUERY)
            if not extracted:
                continue
            text = str(extracted.get("raw_content") or "").strip()
            if len(text) >= _MIN_TEXT_CHARS:
                candidates.append((text, f"tavily_{depth}"))

    if html_for_hints is None:
        try:
            html_for_hints = _fetch_html(url)
            text = _html_to_text(html_for_hints)
            if len(text.strip()) >= _MIN_TEXT_CHARS:
                candidates.append((text, "httpx"))
            if not spa_hints:
                from openrole.scrapers.spa_hints import extract_spa_hints

                extracted = extract_spa_hints(url, html_for_hints)
                if extracted:
                    spa_hints = extracted
        except UniversalScrapeError:
            pass

    if tavily_configured() and not is_indeed_viewjob:
        from openrole.tools.web_search import search_web

        for query in (url, _search_query_for_url(url)):
            rows = search_web(query, max_results=8)
            combined = _combine_search_rows(rows)
            if len(combined) >= _MIN_TEXT_CHARS:
                label = "tavily_search" if query == url else "tavily_search_enriched"
                candidates.append((combined, label))

    if not candidates:
        host = urlparse(url).netloc.lower()
        hint = ""
        if any(h in host for h in _SPA_HOSTS):
            hint = " This site is JavaScript-heavy — paste the full job description below the URL."
        raise UniversalScrapeError(
            f"Could not extract enough text from {url} "
            f"(Tavily extract/search and direct HTTP all failed or returned too little).{hint}"
        )

    host = urlparse(url).netloc.lower()
    if is_spa_host and len(candidates) > 1:
        text = _merge_candidates(candidates)
        source = "+".join(dict.fromkeys(src for _, src in sorted(candidates, key=lambda i: -len(i[0]))))
    else:
        text, source = max(candidates, key=lambda item: len(item[0]))

    if spa_hints:
        from openrole.scrapers.spa_hints import format_structured_metadata_block

        block = format_structured_metadata_block(spa_hints)
        if block not in text:
            text = f"{block}\n\n{text}"
        if "json_ld" not in source:
            source = f"{source}+json_ld" if source else "json_ld"

    return text[:120_000], source, spa_hints


def _merge_candidates(candidates: list[tuple[str, str]]) -> str:
    """Combine unique paragraphs from multiple fetch sources (SPA career sites)."""
    seen: set[str] = set()
    parts: list[str] = []
    for text, _ in sorted(candidates, key=lambda item: -len(item[0])):
        for block in re.split(r"\n{2,}", text):
            block = block.strip()
            if len(block) < 40:
                continue
            key = re.sub(r"\s+", " ", block.lower())[:120]
            if key in seen:
                continue
            seen.add(key)
            parts.append(block)
    merged = "\n\n".join(parts).strip()
    if len(merged) >= _MIN_TEXT_CHARS:
        return merged
    return max(candidates, key=lambda item: len(item[0]))[0]


def _search_query_for_url(url: str) -> str:
    host = urlparse(url).netloc.lower()
    path = urlparse(url).path
    if "metacareers.com" in host:
        job_id = re.search(r"/(\d+)/?$", path)
        id_part = f" {job_id.group(1)}" if job_id else ""
        return f"site:metacareers.com job details{id_part} locations department Artificial Intelligence"
    if "stripe.com" in host and "/jobs/listing/" in path:
        slug = path.rstrip("/").split("/")[-1].replace("-", " ")
        return f"site:stripe.com jobs {slug} description responsibilities"
    return url


def _combine_search_rows(rows: list[dict]) -> str:
    return "\n\n".join(
        f"{row.get('title') or ''}\n{row.get('content') or ''}"
        for row in rows
        if row.get("content")
    ).strip()


def _fetch_html(url: str) -> str:
    host = urlparse(url).netloc.lower()
    prefer_simple_ua = any(h in host for h in _SPA_HOSTS)
    user_agents: tuple[str, ...]
    if prefer_simple_ua:
        user_agents = _FALLBACK_USER_AGENTS + (_HEADERS["User-Agent"],)
    else:
        user_agents = (_HEADERS["User-Agent"],) + _FALLBACK_USER_AGENTS

    last_error: Exception | None = None
    for user_agent in user_agents:
        try:
            with httpx.Client(timeout=30.0, follow_redirects=True) as client:
                response = client.get(
                    url,
                    headers={**_HEADERS, "User-Agent": user_agent},
                )
                response.raise_for_status()
                return response.text[:500_000]
        except httpx.HTTPError as exc:
            last_error = exc
            continue
    raise UniversalScrapeError(f"HTTP fetch failed for {url}: {last_error}") from last_error


def _html_to_text(html: str) -> str:
    cleaned = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", html)
    cleaned = re.sub(r"(?is)<br\s*/?>", "\n", cleaned)
    cleaned = re.sub(r"(?is)</p>", "\n\n", cleaned)
    cleaned = re.sub(r"(?is)<li[^>]*>", "\n• ", cleaned)
    cleaned = re.sub(r"(?is)<[^>]+>", " ", cleaned)
    cleaned = unescape(cleaned)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()
