"""Prepare scout-discovered jobs for filtering — refetch thin SPA pages, batch LLM enrich."""

from __future__ import annotations

import re
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from openrole.agents.job_ingestion import enrich_parsed_job_with_llm, enrich_parsed_jobs_batch_with_llm
from openrole.config import get_settings
from openrole.llm.tracking import format_llm_activity
from openrole.schemas.job import ParsedJob

_SPA_GARBAGE_MARKERS = (
    '"themeOptions"',
    '"customTheme"',
    '"varTheme"',
    '"@context":"http://schema.org"',
    "Mayo Clinic Job Opportunities",
    "navbar-text-color",
)

_EXTRACT_QUERY = (
    "full job description responsibilities qualifications requirements "
    "visa sponsorship OPT CPT work authorization F-1 STEM"
)


def is_low_quality_job_description(text: str | None) -> bool:
    """True when scraped text is likely SPA shell / JSON — not a usable JD."""
    if not text or not text.strip():
        return True
    stripped = text.strip()
    if len(stripped) < 40:
        return True
    marker_hits = sum(1 for m in _SPA_GARBAGE_MARKERS if m in stripped)
    if marker_hits >= 2:
        return True
    if marker_hits >= 1 and stripped.count("{") > 15:
        return True
    if stripped.count("{") > 25 and stripped.count("{") / max(len(stripped), 1) > 0.015:
        return True
    if re.search(r'"title"\s*:\s*"Visa sponsorship"', stripped, re.I):
        return True
    words = re.findall(r"[a-zA-Z]{4,}", stripped[:8000])
    if len(stripped) > 8000 and len(words) < 120:
        return True
    return False


def refetch_scout_job(parsed: ParsedJob) -> ParsedJob:
    """Re-fetch posting text when universal/httpx returned SPA garbage."""
    url = (parsed.source_url or parsed.apply_url or "").strip()
    if not url:
        return parsed

    meta = dict(parsed.raw_payload or {})
    candidates: list[tuple[str, str]] = []

    from openrole.tools.web_search import extract_url, is_configured

    if is_configured():
        for depth in ("advanced", "basic"):
            extracted = extract_url(url, extract_depth=depth, query=_EXTRACT_QUERY)
            if not extracted:
                continue
            text = str(extracted.get("raw_content") or "").strip()
            if text and not is_low_quality_job_description(text):
                candidates.append((text, f"tavily_{depth}"))

    try:
        from openrole.scrapers.universal import UniversalScrapeError, fetch_from_url

        fresh = fetch_from_url(url, source_platform=parsed.source_platform or "universal")
        fresh_text = (fresh.description or "").strip()
        fetch_src = (fresh.raw_payload or {}).get("universal_fetch", {}).get("source", "universal")
        if fresh_text and not is_low_quality_job_description(fresh_text):
            candidates.append((fresh_text, str(fetch_src)))
    except UniversalScrapeError:
        pass

    if not candidates:
        return parsed

    text, source = max(candidates, key=lambda item: len(item[0]))
    meta["scout_refetch"] = {"source": source, "chars": len(text)}
    return parsed.model_copy(
        update={
            "description": text[:120_000],
            "raw_payload": meta,
        }
    )


def refetch_if_needed(parsed: ParsedJob) -> tuple[ParsedJob, list[str]]:
    """Refetch thin SPA pages before LLM enrichment."""
    warnings: list[str] = []
    if is_low_quality_job_description(parsed.description):
        parsed = refetch_scout_job(parsed)
        if is_low_quality_job_description(parsed.description):
            warnings.append(
                f"Could not fetch clean JD text for {parsed.title} — visa/description may be incomplete."
            )
    return parsed, warnings


@dataclass(frozen=True)
class PendingScoutJob:
    parsed: ParsedJob
    source: str
    search_term: str | None


@dataclass(frozen=True)
class ScoutBatchPrepareResult:
    prepared: list[tuple[ParsedJob, list[str], str, str | None]]
    llm_jobs: int
    llm_batches: int


def batch_prepare_scout_jobs(
    pending: list[PendingScoutJob],
    *,
    batch_size: int | None = None,
    on_progress: Callable[[str], None] | None = None,
) -> ScoutBatchPrepareResult:
    """Refetch if needed, then batch LLM enrich (scout path)."""
    if not pending:
        return ScoutBatchPrepareResult(prepared=[], llm_jobs=0, llm_batches=0)

    settings = get_settings()
    need_refetch = sum(
        1 for item in pending if is_low_quality_job_description(item.parsed.description)
    )
    if on_progress:
        on_progress(
            f"Prepare {len(pending)} candidates — "
            f"{need_refetch} thin/empty JDs to refetch (Tavily + scrape), "
            f"then LLM enrich…"
        )

    refetch_workers = max(1, min(settings.scout_refetch_parallel_workers, len(pending)))
    if refetch_workers == 1:
        refetched: list[ParsedJob] = []
        refetch_warnings: list[list[str]] = []
        for index, item in enumerate(pending):
            if on_progress and need_refetch and (index == 0 or (index + 1) % 10 == 0):
                on_progress(f"Refetch {index + 1}/{need_refetch} thin posting(s)…")
            parsed, warnings = refetch_if_needed(item.parsed)
            refetched.append(parsed)
            refetch_warnings.append(warnings)
    else:
        with ThreadPoolExecutor(max_workers=refetch_workers) as pool:
            pairs = list(pool.map(refetch_if_needed, [item.parsed for item in pending]))
        refetched = [parsed for parsed, _ in pairs]
        refetch_warnings = [warnings for _, warnings in pairs]

    upgraded = sum(1 for parsed in refetched if (parsed.raw_payload or {}).get("scout_refetch"))
    skipped_refetch = len(pending) - need_refetch
    if on_progress:
        on_progress(
            f"Refetch done — {upgraded} upgraded, {skipped_refetch} already had clean JDs "
            f"({refetch_workers} workers)…"
        )

    if settings.llm_configured and len(refetched) > 1:
        size = batch_size or settings.scout_ingestion_batch_size
        batch_calls = (len(refetched) + size - 1) // size
        llm_workers = max(1, min(settings.scout_llm_parallel_workers, 16, batch_calls))
        if on_progress:
            on_progress(
                format_llm_activity(
                    f"batch enrich · {len(refetched)} job(s) · {batch_calls} call(s) · "
                    f"{llm_workers} parallel worker(s)",
                    ingestion=True,
                )
            )
        enriched, api_calls = enrich_parsed_jobs_batch_with_llm(
            refetched,
            batch_size=size,
            max_workers=llm_workers,
            log_activity=False,
        )
        llm_jobs = sum(
            1
            for job, _ in enriched
            if isinstance((job.raw_payload or {}).get("llm_enrich"), dict)
            and (job.raw_payload or {}).get("llm_enrich")
        )
    elif settings.llm_configured:
        if on_progress:
            on_progress(format_llm_activity("ingestion · 1 job", ingestion=True))
        one, w = enrich_parsed_job_with_llm(refetched[0], log_activity=False)
        enriched = [(one, w)]
        api_calls = 1
        llm_jobs = 1 if (one.raw_payload or {}).get("llm_enrich") else 0
    else:
        enriched = [(job, ["LLM not configured — stored without enrichment."]) for job in refetched]
        api_calls = 0
        llm_jobs = 0

    prepared: list[tuple[ParsedJob, list[str], str, str | None]] = []
    for item, (parsed, enrich_warnings), ref_warn in zip(pending, enriched, refetch_warnings):
        warnings = ref_warn + enrich_warnings
        prepared.append((parsed, warnings, item.source, item.search_term))

    return ScoutBatchPrepareResult(
        prepared=prepared,
        llm_jobs=llm_jobs,
        llm_batches=api_calls,
    )


def prepare_scout_parsed_job(parsed: ParsedJob) -> tuple[ParsedJob, list[str]]:
    """Single-job prepare (manual re-ingest / tests)."""
    parsed, warnings = refetch_if_needed(parsed)
    settings = get_settings()
    if settings.llm_configured:
        parsed, enrich_warnings = enrich_parsed_job_with_llm(parsed)
        warnings.extend(enrich_warnings)
    elif is_low_quality_job_description(parsed.description):
        warnings.append(
            "LLM not configured — scout job stored without formatted description or visa analysis."
        )
    return parsed, warnings
