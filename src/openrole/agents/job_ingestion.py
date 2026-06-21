"""Ingest job postings from URLs or pasted descriptions."""

from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from openrole.agents.ingestion_prompts import (
    BATCH_INGESTION_SYSTEM_PROMPT,
    INGESTION_SYSTEM_PROMPT,
    build_batch_ingestion_user_message,
    build_ingestion_user_message,
    scraper_hints_from_parsed,
)
from openrole.agents.experience_fit import experience_fit
from openrole.config import get_settings
from openrole.db.repository import save_parsed_job
from openrole.llm import get_chat_model
from openrole.llm.tracking import format_llm_activity, llm_usage_context
from openrole.schemas.job import ParsedJob
from openrole.scrapers.ats_apis import fetch_from_ats
from openrole.scrapers.handshake_client import (
    HandshakeMCPError,
    HandshakeNotConfiguredError,
    fetch_from_handshake,
)
from openrole.scrapers.page_meta import fetch_page_title, parse_linkedin_title
from openrole.scrapers.url_detect import JobPlatform, detect_job_url
from openrole.scrapers.workday import WorkdayParseError, fetch_from_workday
from openrole.tools import jobspy_client
from openrole.tools.domain_resolver import enrich_parsed_job_domain
from openrole.scrapers.universal import UniversalScrapeError, fetch_from_url


class JobIngestionError(Exception):
    pass


def _experience_mismatch_warning(parsed: ParsedJob) -> str | None:
    settings = get_settings()
    if not settings.scout_filter_experience:
        return None
    blob = f"{parsed.title or ''} {(parsed.description or '')}".lower()
    candidate = settings.candidate_years_experience
    if candidate is None:
        candidate = 2.0
    fits, required, cand = experience_fit(
        job_text=blob,
        title=parsed.title or "",
        candidate_years=float(candidate),
        slack_years=float(settings.scout_experience_slack_years),
    )
    if not fits and required is not None:
        return (
            f"Experience mismatch: role expects ~{required}+ years; "
            f"your profile is ~{cand:.0f} years (scout uses +{settings.scout_experience_slack_years}yr slack)."
        )
    return None


def ingest_job(*, job_url: str | None = None, job_text: str | None = None) -> dict[str, Any]:
    if not job_url and not job_text:
        raise JobIngestionError("Provide a job URL or pasted job description")

    parsed: ParsedJob
    warnings: list[str] = []

    if job_url:
        parsed, warnings = _ingest_from_url(job_url.strip(), job_text)
    else:
        parsed = _ingest_from_text(job_text or "")
        warnings = []

    if get_settings().llm_configured:
        parsed, enrich_warnings = enrich_parsed_job_with_llm(parsed, pasted_text=job_text)
        warnings.extend(enrich_warnings)
    elif job_url:
        warnings.append("LLM not configured — stored raw scrape only (locations/department may be missing).")

    parsed, domain_warnings = enrich_parsed_job_domain(parsed)
    warnings.extend(domain_warnings)

    exp_warning = _experience_mismatch_warning(parsed)
    if exp_warning:
        warnings.append(exp_warning)

    job, company = save_parsed_job(parsed)
    return {
        "status": "ok",
        "job_id": job.id,
        "company_id": company.id,
        "parsed_job": parsed.model_dump(mode="json"),
        "warnings": warnings,
    }


def enrich_parsed_job_with_llm(
    parsed: ParsedJob,
    *,
    pasted_text: str | None = None,
    log_activity: bool = True,
) -> tuple[ParsedJob, list[str]]:
    """Run GLM/ingestion model: format full JD, extract & validate department + locations."""
    raw_content = _raw_content_for_enrich(parsed, pasted_text)
    if not raw_content.strip():
        return parsed, ["LLM enrich skipped — no description text to parse."]

    model = get_chat_model(ingestion=True, temperature=0.1)
    user = build_ingestion_user_message(
        source_url=parsed.source_url,
        source_platform=parsed.source_platform,
        scraper_hints=scraper_hints_from_parsed(parsed),
        raw_content=raw_content,
        pasted_supplement=pasted_text,
    )
    title_snip = (parsed.title or "role")[:48]
    with llm_usage_context(
        log_activity=log_activity,
        detail=f"ingestion · {title_snip}",
        pipeline_step="ingest",
    ):
        response = model.invoke(
            [SystemMessage(content=INGESTION_SYSTEM_PROMPT), HumanMessage(content=user)]
        )
    payload = _parse_json_from_llm(str(response.content))
    return _apply_ingestion_payload(parsed, payload)


def enrich_parsed_jobs_batch_with_llm(
    jobs: list[ParsedJob],
    *,
    batch_size: int | None = None,
    max_workers: int | None = None,
    log_activity: bool = True,
) -> tuple[list[tuple[ParsedJob, list[str]]], int]:
    """Batch LLM enrich for scout — fewer API calls than one-by-one.

    Chunks of ``batch_size`` jobs are sent per LLM call. When ``max_workers`` > 1,
    multiple chunks run in parallel (scout-only; manual ingest stays sequential).

    Returns (results aligned to input order, number of batch API calls made).
    """
    if not jobs:
        return [], 0

    settings = get_settings()
    if not settings.llm_configured:
        return [(job, ["LLM not configured — stored without enrichment."]) for job in jobs], 0

    size = max(1, batch_size or settings.scout_ingestion_batch_size)
    raw_workers = max_workers if max_workers is not None else getattr(
        settings, "scout_llm_parallel_workers", 4
    )
    workers = max(1, min(int(raw_workers), 16))

    chunks: list[tuple[int, list[ParsedJob]]] = [
        (start, jobs[start : start + size]) for start in range(0, len(jobs), size)
    ]
    if workers == 1 or len(chunks) <= 1:
        results: list[tuple[ParsedJob, list[str]]] = []
        api_calls = 0
        for start, chunk in chunks:
            _start, chunk_results, calls = _enrich_jobs_chunk(
                start=start, chunk=chunk, log_activity=log_activity
            )
            results.extend(chunk_results)
            api_calls += calls
        return results, api_calls

    parallel_workers = min(workers, len(chunks))
    results_by_start: dict[int, list[tuple[ParsedJob, list[str]]]] = {}
    api_calls = 0
    with ThreadPoolExecutor(max_workers=parallel_workers) as pool:
        futures = {
            pool.submit(
                _enrich_jobs_chunk,
                start=start,
                chunk=chunk,
                log_activity=log_activity,
            ): start
            for start, chunk in chunks
        }
        for future in as_completed(futures):
            start, chunk_results, calls = future.result()
            results_by_start[start] = chunk_results
            api_calls += calls

    merged: list[tuple[ParsedJob, list[str]]] = []
    for start, _chunk in chunks:
        merged.extend(results_by_start[start])
    return merged, api_calls


def _enrich_jobs_chunk(
    *,
    start: int,
    chunk: list[ParsedJob],
    log_activity: bool,
) -> tuple[int, list[tuple[ParsedJob, list[str]]], int]:
    """Run one batch LLM call for a slice of jobs (thread-safe — own model per call)."""
    model = get_chat_model(ingestion=True, temperature=0.1)
    needs_llm: list[tuple[int, ParsedJob]] = []
    chunk_results: dict[int, tuple[ParsedJob, list[str]]] = {}

    for offset, parsed in enumerate(chunk):
        idx = start + offset
        if _already_llm_enriched(parsed):
            chunk_results[idx] = (parsed, [])
        elif not _raw_content_for_enrich(parsed, None).strip():
            chunk_results[idx] = (parsed, ["LLM enrich skipped — no description text to parse."])
        else:
            needs_llm.append((idx, parsed))

    if not needs_llm:
        ordered = [chunk_results[start + offset] for offset in range(len(chunk))]
        return start, ordered, 0

    batch_input: list[dict[str, Any]] = []
    for batch_idx, (_orig_idx, parsed) in enumerate(needs_llm):
        batch_input.append(
            {
                "job_index": batch_idx,
                "source_url": parsed.source_url,
                "source_platform": parsed.source_platform,
                "scraper_hints": scraper_hints_from_parsed(parsed),
                "raw_content": _raw_content_for_enrich(parsed, None)[:12_000],
            }
        )

    user = build_batch_ingestion_user_message(batch_input)
    batch_detail = f"batch ingestion · {len(batch_input)} job(s)"
    with llm_usage_context(
        log_activity=log_activity,
        detail=batch_detail,
        pipeline_step="scout_ingest",
    ):
        response = model.invoke(
            [SystemMessage(content=BATCH_INGESTION_SYSTEM_PROMPT), HumanMessage(content=user)]
        )
    payload = _parse_json_from_llm(str(response.content))
    job_payloads = payload.get("jobs") if isinstance(payload, dict) else None
    if not isinstance(job_payloads, list):
        raise JobIngestionError("Batch LLM response must include a jobs array")

    by_index: dict[int, dict[str, Any]] = {}
    for item in job_payloads:
        if isinstance(item, dict) and isinstance(item.get("job_index"), int):
            by_index[int(item["job_index"])] = item

    for batch_idx, (orig_idx, parsed) in enumerate(needs_llm):
        item_payload = by_index.get(batch_idx)
        if not item_payload:
            chunk_results[orig_idx] = (
                parsed,
                [f"Batch LLM missing result for job_index={batch_idx} — kept raw scrape."],
            )
            continue
        chunk_results[orig_idx] = _apply_ingestion_payload(parsed, item_payload)

    ordered = [chunk_results[start + offset] for offset in range(len(chunk))]
    return start, ordered, 1


def _already_llm_enriched(parsed: ParsedJob) -> bool:
    raw = parsed.raw_payload or {}
    return isinstance(raw.get("llm_enrich"), dict) and bool(raw["llm_enrich"])


def _apply_ingestion_payload(
    parsed: ParsedJob,
    payload: dict[str, Any],
) -> tuple[ParsedJob, list[str]]:
    warnings = list(payload.get("warnings") or [])

    title = payload.get("title") or parsed.title
    company_name = payload.get("company_name") or parsed.company_name
    department = payload.get("department") or parsed.department
    locations = _coerce_locations(payload.get("locations")) or list(parsed.locations or [])
    description = payload.get("description_html") or payload.get("description") or parsed.description

    if not locations:
        warnings.append("No locations extracted — check posting or re-ingest with pasted JD.")
    if not department:
        warnings.append("No department inferred — people search may be broader.")

    dept_val = payload.get("department_validation")
    if dept_val == "corrected":
        warnings.append(f"Department corrected by LLM: {payload.get('department_notes', '')}")
    loc_val = payload.get("locations_validation")
    if loc_val == "corrected":
        warnings.append(f"Locations corrected by LLM: {payload.get('location_notes', '')}")

    visa_status = _normalize_visa_status(payload.get("visa_status"))
    if visa_status == "unknown":
        warnings.append(
            "Visa/CPT/OPT/sponsorship not mentioned in posting — verify before applying on F-1."
        )
    elif visa_status == "ineligible":
        warnings.append(
            "Posting indicates no sponsorship or US-only work authorization — likely not F-1 friendly."
        )

    meta = dict(parsed.raw_payload or {})
    meta["llm_enrich"] = {
        k: payload.get(k)
        for k in (
            "department_confidence",
            "department_validation",
            "department_notes",
            "locations_validation",
            "location_notes",
            "accepts_cpt",
            "accepts_opt",
            "stem_opt_eligible",
            "will_sponsor",
            "work_auth_us_only",
            "visa_status",
            "visa_confidence",
            "visa_validation",
            "visa_notes",
            "visa_evidence",
        )
    }
    if visa_status:
        meta["llm_enrich"]["visa_status"] = visa_status

    return (
        ParsedJob(
            title=str(title)[:512],
            company_name=str(company_name)[:512],
            description=description,
            department=department,
            locations=locations,
            company_domain=payload.get("company_domain") or parsed.company_domain,
            source_url=parsed.source_url,
            source_platform=parsed.source_platform,
            apply_url=parsed.apply_url,
            external_id=parsed.external_id,
            posted_at=parsed.posted_at,
            raw_payload=meta,
        ),
        warnings,
    )


def _raw_content_for_enrich(parsed: ParsedJob, pasted_text: str | None) -> str:
    """Best available source text for the enrichment LLM."""
    if pasted_text and pasted_text.strip():
        if parsed.description and len(parsed.description) > len(pasted_text) * 1.2:
            return (
                f"{pasted_text.strip()}\n\n--- scraper description ---\n{parsed.description}"
            )[:120_000]
        return pasted_text.strip()[:120_000]

    raw = parsed.raw_payload or {}
    if isinstance(raw, dict):
        gh_content = raw.get("content")
        if isinstance(gh_content, str) and gh_content.strip():
            return gh_content[:120_000]
        lever_desc = raw.get("description") or raw.get("descriptionPlain")
        if isinstance(lever_desc, str) and lever_desc.strip():
            return lever_desc[:120_000]
        ashby = raw.get("descriptionHtml") or raw.get("descriptionPlain")
        if isinstance(ashby, str) and ashby.strip():
            return ashby[:120_000]

    if parsed.description and parsed.description.strip():
        return parsed.description.strip()[:120_000]
    return ""


def _normalize_visa_status(value: Any) -> str | None:
    if value is None:
        return None
    status = str(value).strip().lower()
    if status in ("eligible", "ineligible", "unknown"):
        return status
    return None


def _coerce_locations(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        s = str(item).strip()
        if s and s not in out:
            out.append(s)
    return out


def _ingest_from_url(url: str, fallback_text: str | None) -> tuple[ParsedJob, list[str]]:
    info = detect_job_url(url)
    warnings: list[str] = []

    if info.platform in (JobPlatform.GREENHOUSE, JobPlatform.LEVER, JobPlatform.ASHBY):
        parsed = fetch_from_ats(info)
        warnings.append(f"ATS API fetch ({info.platform.value}); LLM will validate and format.")
        return parsed, warnings

    if info.platform == JobPlatform.LINKEDIN:
        if not jobspy_client.is_available():
            if fallback_text:
                return _ingest_from_text(fallback_text, source_url=url), [
                    jobspy_client.jobspy_install_hint(),
                    "Used pasted text because JobSpy is missing.",
                ]
            raise JobIngestionError(jobspy_client.jobspy_install_hint())

        title, company = None, None
        page_title = fetch_page_title(url)
        if page_title:
            title, company = parse_linkedin_title(page_title)
        if fallback_text and (not title or not company):
            skeleton = _skeleton_from_text(fallback_text, source_url=url)
            title = title or skeleton.title
            company = company or skeleton.company_name
        try:
            parsed = jobspy_client.fetch_linkedin_by_search(
                company=company,
                title=title,
                linkedin_job_id=info.job_id,
                source_url=url,
            )
            parsed.source_url = url
            warnings.append(
                "LinkedIn matched via JobSpy search; verify title/company if results look wrong."
            )
            return parsed, warnings
        except ImportError as exc:
            raise JobIngestionError(str(exc)) from exc
        except Exception as exc:
            if fallback_text:
                return _ingest_from_text(fallback_text, source_url=url), [
                    f"JobSpy failed ({exc}); used pasted text instead."
                ]
            if jobspy_client.is_available() and title:
                try:
                    parsed = jobspy_client.fetch_indeed_by_search(
                        company=company,
                        title=title,
                        source_url=url,
                    )
                    parsed.source_url = url
                    parsed.source_platform = JobPlatform.LINKEDIN.value
                    return parsed, [
                        "LinkedIn blocked/rate-limited; matched via Indeed JobSpy search instead.",
                    ]
                except Exception:
                    pass
            raise JobIngestionError(
                "LinkedIn ingestion failed (JobSpy search can rate-limit). "
                "Paste the full job description below and retry."
            ) from exc

    if info.platform == JobPlatform.INDEED:
        from openrole.scrapers.indeed_client import IndeedFetchError, fetch_indeed_by_job_key

        if info.job_id:
            try:
                parsed = fetch_indeed_by_job_key(info.job_id, source_url=url)
                return parsed, ["Indeed fetched directly by job key (mobile viewjob)."]
            except IndeedFetchError as direct_exc:
                direct_error = str(direct_exc)
        else:
            direct_error = None

        if not jobspy_client.is_available():
            if fallback_text:
                return _ingest_from_text(fallback_text, source_url=url), [
                    "JobSpy not installed; used pasted text.",
                ]
            raise JobIngestionError(jobspy_client.jobspy_install_hint())
        try:
            parsed = jobspy_client.fetch_indeed_by_search(
                indeed_job_id=info.job_id,
                source_url=url,
            )
            parsed.source_url = url
            return parsed, ["Indeed matched via JobSpy search; verify the listing."]
        except Exception as exc:
            if fallback_text:
                return _ingest_from_text(fallback_text, source_url=url), [
                    f"Indeed fetch failed ({exc}); used pasted text.",
                ]
            hint = direct_error or str(exc)
            raise JobIngestionError(
                f"Indeed ingestion failed ({hint}). Paste the full job description below."
            ) from exc

    if info.platform == JobPlatform.WORKDAY:
        try:
            return fetch_from_workday(info), ["Workday fetched via public CXS API."]
        except WorkdayParseError as exc:
            if fallback_text:
                return _ingest_from_text(fallback_text, source_url=url), [
                    f"Workday API failed ({exc}); used pasted text."
                ]
            raise JobIngestionError(str(exc)) from exc

    if info.platform == JobPlatform.HANDSHAKE:
        from openrole.scrapers.daemon_manager import managed_daemons

        try:
            with managed_daemons("handshake"):
                parsed = fetch_from_handshake(info)
            return parsed, ["Handshake fetched via local MCP (on-demand daemon)."]
        except HandshakeNotConfiguredError as exc:
            if fallback_text:
                parsed = _ingest_from_text(fallback_text, source_url=url)
                parsed.source_platform = JobPlatform.HANDSHAKE.value
                return parsed, [str(exc), "Used pasted text as fallback."]
            raise JobIngestionError(str(exc)) from exc
        except HandshakeMCPError as exc:
            if fallback_text:
                parsed = _ingest_from_text(fallback_text, source_url=url)
                parsed.source_platform = JobPlatform.HANDSHAKE.value
                return parsed, [str(exc), "Used pasted text as fallback."]
            raise JobIngestionError(str(exc)) from exc

    try:
        parsed = fetch_from_url(url)
        fetch_src = (parsed.raw_payload or {}).get("universal_fetch", {}).get("source", "?")
        return parsed, [f"Unknown platform; fetched via universal scraper ({fetch_src})."]
    except UniversalScrapeError as exc:
        if fallback_text:
            return _ingest_from_text(fallback_text, source_url=url), [
                f"Universal fetch failed ({exc}); parsed from pasted text.",
            ]
        raise JobIngestionError(
            f"Could not fetch job page ({exc}). "
            "For JavaScript career sites (Meta, Stripe, etc.), paste the full job description "
            "in the text box below the URL and click Ingest again."
        ) from exc


def parse_job_page_text(
    text: str,
    *,
    source_url: str,
    source_platform: str,
    spa_hints: dict | None = None,
) -> ParsedJob:
    """Extract structured job fields from page text (universal scraper entry)."""
    cleaned = text.strip()
    if not cleaned:
        raise JobIngestionError("Page text is empty")

    hints = spa_hints or {}
    title = hints.get("title") or "Unknown role"
    company = hints.get("company_name") or "Unknown company"
    locations = list(hints.get("locations") or [])
    department = hints.get("department")

    skeleton = ParsedJob(
        title=str(title)[:512],
        company_name=str(company)[:512],
        description=cleaned,
        department=department,
        locations=locations,
        source_url=source_url,
        source_platform=source_platform,
        apply_url=source_url,
        raw_payload={"universal_fetch_text": cleaned, "spa_hints": hints or None},
    )
    if not get_settings().llm_configured:
        parsed = _heuristic_parse(cleaned)
        parsed.source_url = source_url
        parsed.source_platform = source_platform
        return parsed
    return skeleton


def _ingest_from_text(text: str, source_url: str | None = None) -> ParsedJob:
    return _skeleton_from_text(text, source_url=source_url)


def _skeleton_from_text(text: str, source_url: str | None = None) -> ParsedJob:
    cleaned = text.strip()
    if not cleaned:
        raise JobIngestionError("Job description text is empty")
    platform = "text"
    if source_url:
        platform = detect_job_url(source_url).platform.value
    heuristic = _heuristic_parse(cleaned)
    return ParsedJob(
        title=heuristic.title,
        company_name=heuristic.company_name,
        description=cleaned,
        source_url=source_url,
        source_platform=platform,
        apply_url=source_url,
        raw_payload={"pasted_text": True},
    )


def _heuristic_parse(text: str) -> ParsedJob:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    title = lines[0][:512] if lines else "Unknown role"
    company = "Unknown company"
    for line in lines[:10]:
        if line.lower().startswith("company:"):
            company = line.split(":", 1)[1].strip()
            break
    return ParsedJob(
        title=title,
        company_name=company,
        description=text,
        source_platform="text",
        raw_payload={"heuristic": True},
    )


def _parse_json_from_llm(content: str) -> dict[str, Any]:
    content = content.strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise JobIngestionError("LLM returned invalid JSON for job extraction") from exc
    if not isinstance(data, dict):
        raise JobIngestionError("LLM job extraction must be a JSON object")
    return data
