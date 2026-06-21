"""Job Scout agent (Phase B) — discover, score, ingest, sync."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from collections.abc import Callable
from typing import Any

from openrole.agents.job_scorer import should_run_resume_analysis
from openrole.agents.scout_filter import (
    RejectReason,
    default_scout_search_terms,
    evaluate_scout_job,
)
from openrole.agents.scout_job_prepare import PendingScoutJob, batch_prepare_scout_jobs
from openrole.agents.scout_budget import ScoutRunBudget, select_jobs_matching_terms
from openrole.agents.scout_rotation import (
    mark_company_scouted,
    mark_company_tavily_scouted,
    select_companies_for_ats_scout,
)
from openrole.config import get_settings
from openrole.db.repository import (
    list_companies_with_scout_metadata,
    load_known_job_urls,
    save_scout_discovered_job,
    set_job_notion_page_id,
)
from openrole.db.session import session_scope
from openrole.schemas.scout import ScoutHit, ScoutRunReport
from openrole.scrapers.career_sites import discover_from_company_metadata
from openrole.sync.mappers import job_to_tracker_row
from openrole.sync.notion import notion_configured, sync_tracker_rows_to_notion
from openrole.sync.sheets import sync_tracker_rows_to_sheets
from openrole.tools import jobspy_client
from openrole.tools.scout_context import load_scout_context


class JobScoutError(Exception):
    pass


def run_job_scout(
    *,
    resume_label: str | None = None,
    search_terms: list[str] | None = None,
    location: str | None = None,
    sites: tuple[str, ...] = ("indeed", "linkedin"),
    results_per_term: int | None = None,
    min_score: int | None = None,
    include_ats_boards: bool = True,
    include_career_sites: bool = True,
    include_tavily: bool | None = None,
    include_handshake: bool = True,
    run_resume_analysis: bool = False,
    require_opt_mention: bool | None = None,
    sync_notion: bool | None = None,
    sync_sheets: bool | None = None,
    dry_run: bool = False,
    trigger: str = "manual",
    on_progress: Callable[[str], None] | None = None,
) -> ScoutRunReport:
    """Discover jobs, filter by selected resume + OPT, score, ingest."""
    settings = get_settings()
    run_id = str(uuid.uuid4())
    started = datetime.now(timezone.utc)
    profile = load_scout_context(resume_label=resume_label)
    profile["visa_status"] = settings.candidate_visa_status

    if require_opt_mention is not None:
        settings = settings.model_copy(update={"scout_require_opt_mention": require_opt_mention})

    terms = search_terms or default_scout_search_terms(profile, settings)
    loc = location or settings.scout_search_location
    min_relevance = min_score if min_score is not None else settings.scout_min_relevance_score
    wanted = results_per_term or settings.scout_results_per_term
    resume_threshold = settings.scout_resume_analysis_threshold
    use_tavily = include_tavily if include_tavily is not None else settings.scout_tavily_enabled
    budget = ScoutRunBudget.from_settings(results_per_term=wanted, search_terms=terms)

    with session_scope() as session:
        known_urls = load_known_job_urls(session)
        all_companies = list_companies_with_scout_metadata(session)

    report = ScoutRunReport(
        run_id=run_id,
        started_at=started,
        search_terms=terms,
        resume_label=profile.get("selected_resume_label"),
        trigger=trigger,
        target_new_ingests=budget.target_new_ingests,
    )
    scout_prof = profile.get("scout_resume_profile")
    if scout_prof is not None and hasattr(scout_prof, "to_dict"):
        report.resume_scout_profile = scout_prof.to_dict()

    hits: list[ScoutHit] = []
    pending: list[PendingScoutJob] = []
    errors: list[str] = list(profile.get("warnings") or [])

    def _progress(msg: str) -> None:
        if on_progress:
            on_progress(msg)

    def _candidate_cap_reached() -> bool:
        return len(pending) >= budget.max_candidate_hits

    def _ingest_cap_reached() -> bool:
        if dry_run:
            return report.ingested_new >= budget.target_new_ingests
        return report.ingested_new >= budget.target_new_ingests

    def _consider(parsed, *, source: str, search_term: str | None) -> None:
        if _candidate_cap_reached():
            return
        report.discovered += 1
        url = (parsed.source_url or parsed.apply_url or "").strip()
        if url and url in known_urls:
            report.skipped_already_seen += 1
            return

        pre = evaluate_scout_job(
            parsed,
            profile=profile,
            search_term=search_term,
            settings=settings,
            skip_opt=True,
        )
        if not pre.passed:
            _record_filter_skip(report, pre.reject_reason)
            return

        if _candidate_cap_reached():
            return

        pending.append(
            PendingScoutJob(parsed=parsed, source=source, search_term=search_term)
        )

    for term in terms:
        if _candidate_cap_reached():
            break
        site_label = "+".join(sites)
        _progress(f"JobSpy ({site_label}): searching «{term}»…")
        try:
            parsed_jobs = jobspy_client.search_jobs(
                search_term=term,
                location=loc,
                sites=sites,
                results_wanted=wanted,
                fetch_descriptions=True,
            )
            _progress(f"JobSpy ({site_label}): {len(parsed_jobs)} hit(s) for «{term}»")
            for parsed in parsed_jobs:
                if _candidate_cap_reached():
                    break
                _consider(
                    parsed,
                    source=f"jobspy_{sites[0] if len(sites) == 1 else 'multi'}",
                    search_term=term,
                )
        except Exception as exc:
            errors.append(f"JobSpy '{term}': {exc}")

    if include_handshake and not _candidate_cap_reached():
        from openrole.scrapers.daemon_manager import managed_daemons
        from openrole.scrapers.handshake_client import (
            HandshakeNotConfiguredError,
            handshake_ready,
            search_handshake_jobs,
        )

        if not handshake_ready():
            msg = "Handshake skipped — log in via sidebar or run handshake_login.py"
            errors.append(msg)
            _progress(msg)
        else:
            per_term = max(3, wanted // max(len(terms), 1))
            with managed_daemons("handshake"):
                for term in terms:
                    if _candidate_cap_reached():
                        break
                    _progress(f"Handshake: searching «{term}»…")
                    try:
                        hs_jobs, hs_diag = search_handshake_jobs(
                            keywords=term,
                            location=loc if loc != "United States" else None,
                            max_pages=1,
                            max_jobs=per_term,
                            fetch_details=False,
                        )
                        if hs_jobs:
                            _progress(f"Handshake: {len(hs_jobs)} hit(s) for «{term}»")
                        elif hs_diag:
                            _progress(f"Handshake: 0 hits for «{term}» — {hs_diag}")
                            errors.append(f"Handshake «{term}»: {hs_diag}")
                        else:
                            _progress(f"Handshake: 0 hits for «{term}»")
                        for parsed in hs_jobs:
                            if _candidate_cap_reached():
                                break
                            _consider(parsed, source="handshake", search_term=term)
                    except HandshakeNotConfiguredError as exc:
                        errors.append(f"Handshake: {exc}")
                        break
                    except Exception as exc:
                        errors.append(f"Handshake '{term}': {exc}")

    if use_tavily and not _candidate_cap_reached():
        from openrole.tools.web_search import is_configured as tavily_ready

        if tavily_ready():
            from openrole.agents.scout_rotation import select_companies_for_tavily_scout
            from openrole.agents.tavily_job_discovery import discover_jobs_via_tavily

            tavily_cos, tavily_skipped, tavily_stale = select_companies_for_tavily_scout(
                all_companies,
                max_per_run=budget.max_tavily_companies,
                min_hours_between=float(settings.scout_company_rescout_hours),
            )
            report.companies_scouted_tavily = len(tavily_cos)
            report.companies_skipped_tavily_rotation = tavily_skipped
            if tavily_stale:
                _progress(
                    f"Tavily: all {tavily_skipped} on cooldown — searching {len(tavily_cos)} stalest…"
                )
            else:
                _progress(
                    f"Tavily: {len(tavily_cos)} companies ({tavily_skipped} on rotation cooldown)…"
                )
            try:
                tavily_hits, tavily_warnings = discover_jobs_via_tavily(
                    search_terms=terms,
                    companies=tavily_cos,
                    settings=settings,
                    max_companies=budget.max_tavily_companies,
                    max_total_hits=budget.max_tavily_url_hits,
                    max_results_per_query=budget.max_tavily_results_per_query,
                    compact_queries=budget.use_compact_tavily_queries,
                    on_progress=_progress,
                )
                _progress(f"Tavily: {len(tavily_hits)} candidate URL(s)")
                report.warnings.extend(tavily_warnings[:8])
                for th in tavily_hits:
                    if _candidate_cap_reached():
                        break
                    _consider(
                        th.parsed,
                        source=th.source,
                        search_term=th.search_term,
                    )
                tavily_ids = [c.id for c in tavily_cos if c.id]
                if tavily_ids:
                    from openrole.db.models import Company

                    with session_scope() as session:
                        for cid in tavily_ids:
                            db_co = session.get(Company, cid)
                            if db_co is not None:
                                mark_company_tavily_scouted(db_co)
            except Exception as exc:
                errors.append(f"Tavily job discovery: {exc}")
        else:
            errors.append("Tavily not configured — set TAVILY_API_KEY for ATS/careers job search.")

    if (include_ats_boards or include_career_sites) and not _candidate_cap_reached():
        with session_scope() as session:
            all_companies = list_companies_with_scout_metadata(session)
            to_scout, skipped_rot, ats_stale = select_companies_for_ats_scout(
                all_companies,
                max_per_run=budget.max_ats_companies,
                min_hours_between=float(settings.scout_company_rescout_hours),
            )
            report.companies_skipped_rotation = skipped_rot
            report.companies_scouted_ats = len(to_scout)
            if ats_stale:
                _progress(
                    f"ATS boards: all {skipped_rot} on cooldown — scanning {len(to_scout)} stalest…"
                )
            elif to_scout:
                _progress(
                    f"ATS boards: {len(to_scout)} companies ({skipped_rot} on cooldown)…"
                )
            elif skipped_rot:
                _progress(f"ATS boards: all {skipped_rot} on cooldown — none to scan")
            else:
                _progress("ATS boards: no scout targets configured")

            for company in to_scout:
                if _candidate_cap_reached():
                    break
                meta = company.metadata_json or {}
                if not meta and not include_career_sites:
                    continue
                try:
                    discovered = discover_from_company_metadata(
                        company_name=company.name,
                        domain=company.domain,
                        metadata=meta if include_ats_boards else {"careers_url": meta.get("careers_url")},
                    )
                    discovered = select_jobs_matching_terms(
                        discovered,
                        terms,
                        limit=budget.max_jobs_per_ats_board,
                    )
                    for parsed in discovered:
                        if _candidate_cap_reached():
                            break
                        source = (
                            "careers_url"
                            if parsed.source_platform == "careers_page"
                            else "ats_board"
                        )
                        _consider(parsed, source=source, search_term=terms[0] if terms else None)
                    mark_company_scouted(company)
                    session.flush()
                except Exception as exc:
                    errors.append(f"ATS/careers {company.name}: {exc}")

    if pending:
        if len(pending) > budget.max_llm_prepare:
            _progress(
                f"Prepare capped at {budget.max_llm_prepare} of {len(pending)} candidates for LLM…"
            )
            pending = pending[: budget.max_llm_prepare]
        _progress(
            f"Prepare: {len(pending)} candidate(s) — refetch thin JDs + parallel LLM enrich…"
        )
        try:
            batch_result = batch_prepare_scout_jobs(
                pending,
                batch_size=settings.scout_ingestion_batch_size,
                on_progress=_progress,
            )
            report.scout_llm_enriched = batch_result.llm_jobs
            report.scout_llm_batches = batch_result.llm_batches
            for parsed, prep_warnings, source, search_term in batch_result.prepared:
                report.warnings.extend(prep_warnings[:2])
                verdict = evaluate_scout_job(
                    parsed, profile=profile, search_term=search_term, settings=settings
                )
                if not verdict.passed:
                    _record_filter_skip(report, verdict.reject_reason)
                    continue
                hits.append(
                    ScoutHit(
                        parsed=parsed,
                        source=source,
                        relevance_score=verdict.relevance_score,
                        search_term=search_term,
                        role_families=list(verdict.role_families),
                        opt_status=verdict.opt_status,
                    )
                )
        except Exception as exc:
            errors.append(f"Scout batch prepare: {exc}")

    report.errors = errors

    best_by_url: dict[str, ScoutHit] = {}
    for hit in hits:
        url = hit.parsed.source_url
        if not url:
            continue
        prev = best_by_url.get(url)
        if prev is None or hit.relevance_score > prev.relevance_score:
            best_by_url[url] = hit

    ingested_rows: list[dict[str, Any]] = []
    top_hits: list[dict[str, Any]] = []

    for hit in sorted(best_by_url.values(), key=lambda h: h.relevance_score, reverse=True):
        if _ingest_cap_reached():
            break
        if hit.relevance_score < min_relevance:
            report.skipped_low_score += 1
            continue

        scout_meta = {
            "run_id": run_id,
            "source": hit.source,
            "search_term": hit.search_term,
            "relevance_score": hit.relevance_score,
            "role_families": hit.role_families,
            "opt_status": hit.opt_status,
            "opt_needs_verification": hit.opt_status == "unknown",
            "resume_label": profile.get("selected_resume_label"),
            "discovered_at": started.isoformat(),
        }

        if dry_run:
            report.ingested_new += 1
            top_hits.append(_hit_summary(hit, job_id=None))
            continue

        job, company, is_new = save_scout_discovered_job(hit.parsed, scout_meta=scout_meta)
        if is_new:
            report.ingested_new += 1
            if job.source_url:
                known_urls.add(job.source_url.strip())
        else:
            report.updated_existing += 1
        row = job_to_tracker_row(job, company_name=company.name)
        from openrole.db.repository import get_job_notion_page_id

        notion_pid = get_job_notion_page_id(job)
        if notion_pid:
            row["notion_page_id"] = notion_pid
        ingested_rows.append(row)
        top_hits.append(_hit_summary(hit, job_id=job.id))

        if run_resume_analysis and should_run_resume_analysis(
            hit.relevance_score, threshold=resume_threshold
        ):
            try:
                from openrole.agents.resume_optimizer import optimize_resume_for_job

                optimize_resume_for_job(
                    job_id=job.id,
                    resume_label=profile.get("selected_resume_label"),
                )
                report.resume_scored += 1
            except Exception as exc:
                report.warnings.append(f"Resume analysis {job.title}: {exc}")

    report.top_hits = top_hits[:25]

    do_notion = sync_notion if sync_notion is not None else notion_configured()
    do_sheets = sync_sheets if sync_sheets is not None else True

    if ingested_rows and not dry_run:
        if do_notion and notion_configured():
            notion_result = sync_tracker_rows_to_notion(ingested_rows)
            report.notion_synced = notion_result.get("synced", 0)
            if notion_result.get("errors"):
                report.warnings.extend(notion_result["errors"][:5])
            for item in notion_result.get("page_ids") or []:
                jid, pid = item.get("job_id"), item.get("page_id")
                if jid and pid:
                    with session_scope() as session:
                        set_job_notion_page_id(session, jid, pid)
        if do_sheets:
            sheets_result = sync_tracker_rows_to_sheets(ingested_rows)
            report.sheets_synced = sheets_result.get("synced", 0)
            if sheets_result.get("sheets_error"):
                report.warnings.append(str(sheets_result["sheets_error"]))

    report.finished_at = datetime.now(timezone.utc)
    report.stopped_at_budget = _candidate_cap_reached() or _ingest_cap_reached()
    from openrole.llm.tracking import format_llm_activity

    _progress(
        f"Done — ingested {report.ingested_new}/{budget.target_new_ingests}, "
        f"discovered {report.discovered}, "
        f"{format_llm_activity(f'enriched {report.scout_llm_enriched} job(s)', ingestion=True)}"
    )

    from openrole.scheduler.scout_log import append_scout_run

    append_scout_run(report.to_dict(), trigger=trigger)
    return report


def _record_filter_skip(report: ScoutRunReport, reason: RejectReason | None) -> None:
    if reason == RejectReason.NOT_SOFTWARE:
        report.skipped_not_software += 1
    elif reason == RejectReason.RESUME_MISMATCH:
        report.skipped_resume_mismatch += 1
    elif reason == RejectReason.EXPERIENCE_MISMATCH:
        report.skipped_experience_mismatch += 1
    elif reason in (RejectReason.OPT_INELIGIBLE, RejectReason.OPT_UNKNOWN):
        report.skipped_opt += 1


def _hit_summary(hit: ScoutHit, *, job_id: str | None) -> dict[str, Any]:
    return {
        "job_id": job_id,
        "title": hit.parsed.title,
        "company": hit.parsed.company_name,
        "url": hit.parsed.source_url,
        "score": hit.relevance_score,
        "matched": ",".join(hit.role_families or []),
        "opt": hit.opt_status,
        "source": hit.source,
        "search_term": hit.search_term,
    }
