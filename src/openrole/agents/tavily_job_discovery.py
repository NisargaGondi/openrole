"""Discover job postings via Tavily web search (Greenhouse, Lever, Ashby, Workday, careers sites).

Query templates (no LLM — sent directly to Tavily Search API):

  ats_boards:
    "{term}" site:boards.greenhouse.io OR site:jobs.lever.co OR site:jobs.ashbyhq.com OR site:myworkdayjobs.com

  company_ats:
    "{company}" "{term}" (greenhouse OR lever OR ashby OR workday OR careers) jobs

  company_domain:
    site:{domain} "{term}" engineer jobs

  company_careers:
    "{company}" careers "{term}" job opening United States

Results are parsed for known ATS/career URLs, optionally enriched via public ATS APIs
or Workday CXS, then returned as ParsedJob objects for the scout filter pipeline.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from openrole.config import Settings, get_settings
from openrole.db.models import Company
from openrole.schemas.job import ParsedJob
from openrole.scrapers.url_detect import JobPlatform, detect_job_url
from openrole.tools.web_search import is_configured, search_web

_MIN_RESULTS_RETRY = 2
_MAX_RESULTS_PER_QUERY = 10

# Documented templates for Settings / debugging (placeholders in braces).
TAVILY_JOB_QUERY_TEMPLATES: dict[str, str] = {
    "ats_boards": (
        '"{term}" (site:boards.greenhouse.io OR site:jobs.lever.co OR '
        "site:jobs.ashbyhq.com OR site:myworkdayjobs.com) jobs United States"
    ),
    "greenhouse_board": 'site:boards.greenhouse.io/{token} "{term}"',
    "company_ats": (
        '"{company}" "{term}" (greenhouse OR lever OR ashby OR workday OR careers) jobs'
    ),
    "company_domain": 'site:{domain} "{term}" engineer jobs',
    "company_careers": '"{company}" careers "{term}" job opening United States',
}

_JOB_URL_RES: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(
            r"https?://boards\.greenhouse\.io/[A-Za-z0-9_-]+/jobs/\d+[^\s\"'<>]*",
            re.I,
        ),
        "greenhouse",
    ),
    (
        re.compile(
            r"https?://(?:[\w.-]+\.)?greenhouse\.io/[A-Za-z0-9_-]+/jobs/\d+[^\s\"'<>]*",
            re.I,
        ),
        "greenhouse",
    ),
    (
        re.compile(
            r"https?://jobs\.lever\.co/[A-Za-z0-9_-]+/[a-f0-9-]+[^\s\"'<>]*",
            re.I,
        ),
        "lever",
    ),
    (
        re.compile(
            r"https?://jobs\.ashbyhq\.com/[A-Za-z0-9_-]+/[a-f0-9-]+[^\s\"'<>]*",
            re.I,
        ),
        "ashby",
    ),
    (
        re.compile(
            r"https?://[\w.-]+\.myworkdayjobs\.com/[^\s\"'<>]*/job/[^\s\"'<>]+",
            re.I,
        ),
        "workday",
    ),
    (
        re.compile(
            r"https?://(?:[\w.-]+\.)?metacareers\.com/jobs/\d+[^\s\"'<>]*",
            re.I,
        ),
        "metacareers",
    ),
    (
        re.compile(
            r"https?://(?:[\w.-]+\.)?stripe\.com/jobs/listing/[^\s\"'<>/]+[^\s\"'<>]*",
            re.I,
        ),
        "stripe_careers",
    ),
    (
        re.compile(
            r"https?://[\w.-]+/careers[^\s\"'<>]*/(?:job|jobs)/[^\s\"'<>]+",
            re.I,
        ),
        "careers_page",
    ),
]

_SKIP_URL_FRAGMENTS = (
    "/users/sign_in",
    "/login",
    "/privacy",
    "/terms",
    "linkedin.com/company",
    "linkedin.com/in/",
    "facebook.com",
    "twitter.com",
    "youtube.com",
)


@dataclass(frozen=True)
class TavilyJobHit:
    parsed: ParsedJob
    source: str
    search_term: str | None
    query_type: str
    tavily_url: str | None = None


def discover_jobs_via_tavily(
    *,
    search_terms: list[str],
    companies: list[Company] | None = None,
    settings: Settings | None = None,
    max_companies: int | None = None,
    max_total_hits: int | None = None,
    max_results_per_query: int | None = None,
    compact_queries: bool = False,
    on_progress: Any = None,
) -> tuple[list[TavilyJobHit], list[str]]:
    """Run multi-pass Tavily job discovery across ATS boards and target companies."""
    warnings: list[str] = []
    if not is_configured():
        warnings.append("Tavily not configured — set TAVILY_API_KEY for broad job discovery.")
        return [], warnings

    settings = settings or get_settings()
    terms = [t.strip() for t in search_terms if t and t.strip()]
    if not terms:
        warnings.append("Tavily job discovery: no search terms.")
        return [], warnings

    specs = build_tavily_job_query_specs(
        search_terms=terms,
        companies=companies or [],
        max_companies=max_companies or settings.scout_tavily_companies_per_run,
        compact=compact_queries,
    )
    if not specs:
        warnings.append("Tavily job discovery: no queries built.")
        return [], warnings

    seen_urls: set[str] = set()
    hits: list[TavilyJobHit] = []
    hit_cap = max_total_hits if max_total_hits is not None else 10_000
    per_query = max_results_per_query or _MAX_RESULTS_PER_QUERY

    for spec in specs:
        if len(hits) >= hit_cap:
            warnings.append(f"Tavily jobs: stopped at budget cap ({hit_cap} URLs).")
            break
        qtype = spec["query_type"]
        query = spec["query"]
        if on_progress:
            on_progress(f"Tavily jobs [{qtype}]: searching…")
        rows = _search_query(query, max_results=per_query)
        if len(rows) < _MIN_RESULTS_RETRY:
            if on_progress:
                on_progress(f"Tavily jobs [{qtype}]: retry advanced depth")
            rows = _merge_rows(
                rows,
                _search_query(query, search_depth="advanced", max_results=per_query),
            )

        new_count = 0
        for row in rows:
            if len(hits) >= hit_cap:
                break
            for candidate in _candidates_from_row(row, spec=spec):
                if len(hits) >= hit_cap:
                    break
                key = _normalize_job_url(candidate.url)
                if not key or key in seen_urls:
                    continue
                seen_urls.add(key)
                parsed = lightweight_job_from_candidate(
                    candidate,
                    company_hint=spec.get("company") or candidate.company_hint,
                )
                if parsed is None or not (parsed.title or "").strip():
                    continue
                if _looks_like_board_home(parsed.source_url or ""):
                    continue
                hits.append(
                    TavilyJobHit(
                        parsed=parsed,
                        source=f"tavily_{qtype}",
                        search_term=spec.get("search_term"),
                        query_type=qtype,
                        tavily_url=candidate.url,
                    )
                )
                new_count += 1

        if on_progress:
            on_progress(f"Tavily jobs [{qtype}]: +{new_count} posting(s)")
        warnings.append(
            f"Tavily jobs [{qtype}]: +{new_count} — `{query[:90]}{'…' if len(query) > 90 else ''}`"
        )

    if hits:
        warnings.append(f"Tavily jobs total: {len(hits)} unique posting URL(s).")
    else:
        warnings.append("Tavily jobs: no posting URLs found this run.")

    return hits, warnings


def build_tavily_job_query_specs(
    *,
    search_terms: list[str],
    companies: list[Company],
    max_companies: int,
    compact: bool = False,
) -> list[dict[str, str]]:
    """Build ordered Tavily job search specs (broad ATS → per-company)."""
    specs: list[dict[str, str]] = []
    seen_queries: set[str] = set()

    def add(query_type: str, query: str, **extra: str) -> None:
        q = " ".join(query.split())
        if not q or q in seen_queries:
            return
        seen_queries.add(q)
        specs.append({"query_type": query_type, "query": q, **extra})

    term_limit = 2 if compact else 6
    for term in search_terms[:term_limit]:
        add(
            "ats_boards",
            TAVILY_JOB_QUERY_TEMPLATES["ats_boards"].format(term=term),
            search_term=term,
        )

    company_specs = _pick_companies_for_tavily(companies, max_companies=max_companies)
    primary_term = search_terms[0]
    secondary_term = search_terms[1] if len(search_terms) > 1 else primary_term
    company_terms = (primary_term,) if compact else (primary_term, secondary_term)

    for company in company_specs:
        name = (company.name or "").strip()
        domain = (company.domain or "").strip().lower()
        meta = company.metadata_json or {}
        if not name:
            continue
        gh_token = meta.get("greenhouse_token") or meta.get("greenhouse_board")
        if gh_token:
            for term in company_terms:
                add(
                    "greenhouse_board",
                    TAVILY_JOB_QUERY_TEMPLATES["greenhouse_board"].format(
                        token=str(gh_token), term=term
                    ),
                    search_term=term,
                    company=name,
                )
        for term in company_terms:
            add(
                "company_ats",
                TAVILY_JOB_QUERY_TEMPLATES["company_ats"].format(company=name, term=term),
                search_term=term,
                company=name,
            )
            if not compact:
                add(
                    "company_careers",
                    TAVILY_JOB_QUERY_TEMPLATES["company_careers"].format(company=name, term=term),
                    search_term=term,
                    company=name,
                )
        if domain and "." in domain and not compact:
            add(
                "company_domain",
                TAVILY_JOB_QUERY_TEMPLATES["company_domain"].format(domain=domain, term=primary_term),
                search_term=primary_term,
                company=name,
            )

    return specs


def lightweight_job_from_candidate(
    candidate: _UrlCandidate,
    *,
    company_hint: str | None,
) -> ParsedJob | None:
    """Fast parse for scout discovery — full fetch/LLM deferred to prepare step."""
    url = candidate.url
    info = detect_job_url(url)
    if info.platform == JobPlatform.GREENHOUSE and info.board_token and info.job_id:
        try:
            from openrole.scrapers.ats_apis import fetch_from_ats

            return _tag_tavily(fetch_from_ats(info), url=url, snippet=candidate.snippet)
        except Exception:
            pass
    if info.platform == JobPlatform.LEVER and info.company_slug and info.job_id:
        try:
            from openrole.scrapers.ats_apis import fetch_from_ats

            return _tag_tavily(fetch_from_ats(info), url=url, snippet=candidate.snippet)
        except Exception:
            pass
    if info.platform == JobPlatform.ASHBY and info.company_slug and info.job_id:
        try:
            from openrole.scrapers.ats_apis import fetch_from_ats

            return _tag_tavily(fetch_from_ats(info), url=url, snippet=candidate.snippet)
        except Exception:
            pass
    return _parsed_from_snippet(
        url,
        company_hint=company_hint or candidate.company_hint,
        title_hint=candidate.title_hint,
        snippet=candidate.snippet,
        platform=candidate.platform or "tavily",
    )


def discover_company_jobs_via_tavily(
    *,
    company_name: str,
    domain: str | None,
    search_terms: list[str],
    careers_url: str | None = None,
) -> list[ParsedJob]:
    """Find individual job URLs for one company (used by career_sites fallback)."""
    if not is_configured():
        return []

    specs: list[dict[str, str]] = []
    term = search_terms[0] if search_terms else "software engineer"
    specs.append(
        {
            "query_type": "company_ats",
            "query": TAVILY_JOB_QUERY_TEMPLATES["company_ats"].format(company=company_name, term=term),
            "search_term": term,
            "company": company_name,
        }
    )
    if domain:
        specs.append(
            {
                "query_type": "company_domain",
                "query": TAVILY_JOB_QUERY_TEMPLATES["company_domain"].format(
                    domain=domain, term=term
                ),
                "search_term": term,
                "company": company_name,
            }
        )
    if careers_url:
        host = urlparse(careers_url).netloc
        if host:
            specs.append(
                {
                    "query_type": "company_careers",
                    "query": f'site:{host} "{term}" jobs',
                    "search_term": term,
                    "company": company_name,
                }
            )

    seen: set[str] = set()
    jobs: list[ParsedJob] = []
    for spec in specs:
        rows = _search_query(spec["query"])
        if len(rows) < _MIN_RESULTS_RETRY:
            rows = _merge_rows(rows, _search_query(spec["query"], search_depth="advanced"))
        for row in rows:
            for candidate in _candidates_from_row(row, spec=spec):
                key = _normalize_job_url(candidate.url)
                if not key or key in seen:
                    continue
                seen.add(key)
                parsed = enrich_job_url(
                    candidate.url,
                    company_hint=company_name,
                    title_hint=candidate.title_hint,
                    snippet=candidate.snippet,
                    platform_hint=candidate.platform,
                )
                if parsed and not _looks_like_board_home(parsed.source_url or ""):
                    jobs.append(parsed)
    return jobs


def enrich_job_url(
    url: str,
    *,
    company_hint: str | None = None,
    title_hint: str | None = None,
    snippet: str | None = None,
    platform_hint: str | None = None,
) -> ParsedJob | None:
    """Resolve a job URL to a ParsedJob — prefer ATS/Workday APIs, else Tavily snippet."""
    url = url.strip()
    if not url or _should_skip_url(url):
        return None

    info = detect_job_url(url)
    platform = platform_hint or (info.platform.value if info.platform != JobPlatform.UNKNOWN else None)

    try:
        if info.platform == JobPlatform.GREENHOUSE and info.board_token and info.job_id:
            from openrole.scrapers.ats_apis import fetch_from_ats

            parsed = fetch_from_ats(info)
            return _tag_tavily(parsed, url=url, snippet=snippet)
        if info.platform == JobPlatform.LEVER and info.company_slug and info.job_id:
            from openrole.scrapers.ats_apis import fetch_from_ats

            parsed = fetch_from_ats(info)
            return _tag_tavily(parsed, url=url, snippet=snippet)
        if info.platform == JobPlatform.ASHBY and info.company_slug and info.job_id:
            from openrole.scrapers.ats_apis import fetch_from_ats

            parsed = fetch_from_ats(info)
            return _tag_tavily(parsed, url=url, snippet=snippet)
        if info.platform == JobPlatform.WORKDAY and "/job/" in url.lower():
            from openrole.scrapers.workday import fetch_from_workday

            parsed = fetch_from_workday(info)
            return _tag_tavily(parsed, url=url, snippet=snippet)
    except Exception:
        pass

    # SPA / custom career sites — lightweight universal fetch when Tavily snippet is thin
    if platform in ("metacareers", "stripe_careers", "careers_page") or info.platform == JobPlatform.UNKNOWN:
        try:
            from openrole.scrapers.universal import UniversalScrapeError, fetch_from_url

            parsed = fetch_from_url(url, source_platform=platform or "universal")
            if company_hint and parsed.company_name in ("Unknown", "", "Unknown Company"):
                parsed = parsed.model_copy(update={"company_name": company_hint})
            return _tag_tavily(parsed, url=url, snippet=snippet)
        except UniversalScrapeError:
            pass

    return _parsed_from_snippet(
        url,
        company_hint=company_hint,
        title_hint=title_hint,
        snippet=snippet,
        platform=platform or "tavily",
    )


@dataclass(frozen=True)
class _UrlCandidate:
    url: str
    title_hint: str | None
    snippet: str | None
    platform: str | None
    company_hint: str | None = None


def _search_query(
    query: str,
    *,
    search_depth: str = "basic",
    max_results: int = _MAX_RESULTS_PER_QUERY,
) -> list[dict[str, Any]]:
    return search_web(
        query,
        max_results=min(max_results, _MAX_RESULTS_PER_QUERY),
        search_depth=search_depth,
    )


def _merge_rows(a: list[dict[str, Any]], b: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    merged: list[dict[str, Any]] = []
    for row in a + b:
        key = (row.get("url") or "") + (row.get("title") or "")
        if key in seen:
            continue
        seen.add(key)
        merged.append(row)
    return merged


def _candidates_from_row(row: dict[str, Any], *, spec: dict[str, str]) -> list[_UrlCandidate]:
    title = str(row.get("title") or "").strip() or None
    snippet = str(row.get("content") or "").strip() or None
    company_hint = spec.get("company")
    urls: list[str] = []
    direct = str(row.get("url") or "").strip()
    if direct:
        urls.append(direct)
    blob = " ".join(filter(None, [direct, title, snippet]))
    urls.extend(extract_job_urls(blob))

    out: list[_UrlCandidate] = []
    seen: set[str] = set()
    for raw in urls:
        url = _clean_url(raw)
        key = _normalize_job_url(url)
        if not key or key in seen or _should_skip_url(url):
            continue
        seen.add(key)
        platform = _platform_for_url(url)
        out.append(
            _UrlCandidate(
                url=url,
                title_hint=_title_from_row(title, url),
                snippet=snippet,
                platform=platform,
                company_hint=company_hint,
            )
        )
    return out


def extract_job_urls(text: str) -> list[str]:
    if not text:
        return []
    found: list[str] = []
    for pattern, _ in _JOB_URL_RES:
        for match in pattern.finditer(text):
            found.append(match.group(0))
    return list(dict.fromkeys(found))


def _pick_companies_for_tavily(companies: list[Company], *, max_companies: int) -> list[Company]:
    """Prefer companies with domain; respect tavily rotation timestamp."""
    from openrole.agents.scout_rotation import select_companies_for_tavily_scout

    selected, _skipped, _stale = select_companies_for_tavily_scout(
        companies,
        max_per_run=max(1, max_companies),
        min_hours_between=float(get_settings().scout_company_rescout_hours),
    )
    return selected


def _normalize_job_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if not parsed.netloc:
        return ""
    path = parsed.path.rstrip("/")
    return f"{parsed.scheme}://{parsed.netloc.lower()}{path}".lower()


def _clean_url(url: str) -> str:
    return url.rstrip(".,;:)\"'").strip()


def _should_skip_url(url: str) -> bool:
    lower = url.lower()
    if any(frag in lower for frag in _SKIP_URL_FRAGMENTS):
        return True
    if "/jobs" in lower and lower.rstrip("/").endswith("/jobs"):
        return True
    return False


def _looks_like_board_home(url: str) -> bool:
    lower = url.lower().rstrip("/")
    if lower.endswith("/jobs") or lower.endswith("/careers"):
        return True
    if "myworkdayjobs.com" in lower and "/job/" not in lower:
        return True
    return False


def _platform_for_url(url: str) -> str | None:
    for pattern, platform in _JOB_URL_RES:
        if pattern.search(url):
            return platform
    info = detect_job_url(url)
    if info.platform != JobPlatform.UNKNOWN:
        return info.platform.value
    return None


def _title_from_row(title: str | None, url: str) -> str | None:
    if title and title.lower() not in ("summary",):
        cleaned = re.sub(r"\s*[|\-–—]\s*.*$", "", title).strip()
        if len(cleaned) >= 4 and cleaned.lower() not in ("jobs", "careers", "job openings"):
            return cleaned
    path = urlparse(url).path.rstrip("/")
    slug = path.split("/")[-1] if path else ""
    if slug and slug not in ("jobs", "job"):
        return slug.replace("-", " ").replace("_", " ").title()
    return title


def _parsed_from_snippet(
    url: str,
    *,
    company_hint: str | None,
    title_hint: str | None,
    snippet: str | None,
    platform: str,
) -> ParsedJob | None:
    title = (title_hint or "Unknown role").strip()
    if title.lower() in ("jobs", "careers", "summary"):
        return None
    company = (company_hint or _company_from_url(url) or "Unknown").strip()
    description = snippet
    if snippet and title and title in snippet:
        description = snippet
    return ParsedJob(
        title=title,
        company_name=company,
        description=description,
        company_domain=_domain_from_url(url),
        source_url=url,
        source_platform=platform,
        apply_url=url,
        raw_payload={
            "_openrole_tavily": True,
            "tavily_snippet": snippet,
            "tavily_discovery": True,
        },
    )


def _tag_tavily(parsed: ParsedJob, *, url: str, snippet: str | None) -> ParsedJob:
    meta = dict(parsed.raw_payload or {})
    meta["_openrole_tavily"] = True
    meta["tavily_discovery"] = True
    meta["tavily_source_url"] = url
    if snippet:
        meta["tavily_snippet"] = snippet
    return parsed.model_copy(update={"raw_payload": meta})


def _company_from_url(url: str) -> str | None:
    host = urlparse(url).netloc.lower()
    if "greenhouse.io" in host:
        parts = [p for p in urlparse(url).path.split("/") if p]
        if parts and parts[0] not in ("jobs", "embed"):
            return parts[0].replace("-", " ").title()
    if "lever.co" in host:
        parts = [p for p in urlparse(url).path.split("/") if p]
        if parts:
            return parts[0].replace("-", " ").title()
    if "ashbyhq.com" in host:
        parts = [p for p in urlparse(url).path.split("/") if p]
        if parts:
            return parts[0].replace("-", " ").title()
    tenant = host.split(".")[0] if host else ""
    if tenant and tenant not in ("www", "jobs", "boards"):
        return tenant.replace("-", " ").title()
    return None


def _domain_from_url(url: str) -> str | None:
    host = urlparse(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    if host in (
        "boards.greenhouse.io",
        "jobs.lever.co",
        "jobs.ashbyhq.com",
    ) or "myworkdayjobs.com" in host:
        return None
    return host or None
