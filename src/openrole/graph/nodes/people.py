"""People discovery nodes."""

from __future__ import annotations

from sqlalchemy import select

from openrole.agents.pipeline_progress import progress_entry, stamp
from openrole.api.activity_store import log as act_log
from openrole.agents.people_discovery import (
    PeopleDiscoveryError,
    extract_context_for_job,
    location_target_from_dict,
    location_target_to_dict,
    rank_people_candidates,
    validate_and_finalize_contacts,
)
from openrole.agents.person_research import dedupe_contacts_for_research
from openrole.config import get_settings
from openrole.db.models import Job
from openrole.db.repository import list_contacts_for_job, save_discovered_contacts
from openrole.db.session import session_scope
from openrole.graph.state import OpenRoleState
from openrole.schemas.contact import DiscoveredContact
from openrole.schemas.job_context import JobSearchContext
from openrole.schemas.pipeline import PipelineOptions


def extract_context_node(state: OpenRoleState) -> dict:
    job_id = state.get("job_id")
    if not job_id:
        return {"errors": ["job_id required for people discovery"]}
    try:
        ctx, loc, warnings = extract_context_for_job(job_id)
        return {
            "search_context": ctx.model_dump(),
            "location_target": location_target_to_dict(loc),
            "pipeline_stage": "context_extracted",
            "stages_completed": ["extract_context"],
            "warnings": warnings,
            **progress_entry("Extracted job department + location context"),
        }
    except PeopleDiscoveryError as exc:
        return {"errors": [str(exc)]}


def discover_candidates_node(state: OpenRoleState) -> dict:
    job_id = state.get("job_id")
    raw_ctx = state.get("search_context")
    raw_loc = state.get("location_target")
    if not job_id or not raw_ctx or not raw_loc:
        return {"errors": ["Missing job_id or search context"]}
    try:
        ctx = JobSearchContext.model_validate(raw_ctx)
        loc = location_target_from_dict(raw_loc)
        opts = PipelineOptions.from_state(state.get("pipeline_options"))
        settings = get_settings()
        include_cs = opts.include_careershift or settings.careershift_people_pipeline
        source_label = "Tavily + CareerShift" if include_cs and not settings.apollo_enabled else (
            "Tavily + CareerShift + Apollo" if include_cs and settings.apollo_enabled
            else "Tavily + Apollo" if settings.apollo_enabled
            else "Tavily"
        )
        progress_lines: list[str] = [stamp(f"Discovering people ({source_label})")]
        from openrole.scrapers.daemon_manager import managed_daemons

        daemon_names: list[str] = []
        if include_cs:
            daemon_names.append("careershift")
        with managed_daemons(*daemon_names):
            candidates, domain, company_name, source_warnings = rank_people_candidates(
                job_id,
                search_context=ctx,
                location_target=loc,
                include_careershift=include_cs,
                on_progress=progress_lines.append,
            )
        progress_lines.append(stamp(f"Discovery complete — {len(candidates)} ranked candidate(s)"))
        return {
            "contact_candidates": [c.model_dump(mode="json") for c in candidates],
            "company_domain": domain,
            "company": {"name": company_name},
            "pipeline_stage": "candidates_ranked",
            "stages_completed": ["discover_candidates"],
            "warnings": source_warnings,
            "progress_log": progress_lines,
        }
    except PeopleDiscoveryError as exc:
        return {"errors": [str(exc)]}


def validate_contacts_node(state: OpenRoleState) -> dict:
    raw_candidates = state.get("contact_candidates") or []
    raw_ctx = state.get("search_context")
    raw_loc = state.get("location_target")
    domain = state.get("company_domain") or ""
    if not raw_ctx or not raw_loc:
        return {"errors": ["Missing context for validation"]}
    if not raw_candidates:
        return {
            "contacts": [],
            "errors": ["Tavily and/or CareerShift returned no candidates for this job"],
            "pipeline_stage": "validate_empty",
            **progress_entry("Validation skipped — no candidates"),
        }

    ctx = JobSearchContext.model_validate(raw_ctx)
    loc = location_target_from_dict(raw_loc)
    candidates = [DiscoveredContact.model_validate(c) for c in raw_candidates]
    job = None
    company_name = (state.get("company") or {}).get("name")
    job_id = state.get("job_id")
    if job_id:
        with session_scope() as session:
            job = session.scalar(select(Job).where(Job.id == job_id).limit(1))
    progress = [stamp(f"Validating {len(candidates)} candidate(s) (location + department)")]
    act_log(progress[0], icon="dot")

    def _on_progress(msg: str) -> None:
        progress.append(msg)
        act_log(msg, icon="dot")

    final, validation, val_warnings = validate_and_finalize_contacts(
        candidates,
        search_context=ctx,
        location_target=loc,
        company_domain=domain,
        job=job,
        company_name=company_name,
        apollo_enrich_limit=0,
        guess_emails=True,
        on_progress=_on_progress,
    )
    progress.append(stamp(f"Validation complete — {len(final)} contact(s) passed filters"))
    errors: list[str] = []
    if not final:
        errors.append(
            "No contacts passed location + department validation. "
            "Check job cities and department in the posting."
        )
    return {
        "contacts": [c.model_dump(mode="json") for c in final],
        "validation_result": validation,
        "pipeline_stage": "contacts_validated",
        "stages_completed": ["validate_contacts"],
        "warnings": val_warnings,
        "errors": errors,
        "progress_log": progress,
        "_live_progress": True,
    }


def persist_contacts_node(state: OpenRoleState) -> dict:
    job_id = state.get("job_id")
    raw = state.get("contacts") or []
    if not job_id or not raw:
        return {
            "contact_count": 0,
            "pipeline_stage": "persist_skipped",
            **progress_entry("Persist skipped — no contacts to save"),
        }

    contacts = [DiscoveredContact.model_validate(c) for c in raw]
    with session_scope() as session:
        job = session.scalar(select(Job).where(Job.id == job_id).limit(1))
        if job is None or not job.company_id:
            return {"errors": ["Job not found for persist"]}
        saved = save_discovered_contacts(
            session,
            company_id=job.company_id,
            contacts=contacts,
            source_job_id=job_id,
        )
        session.commit()

    return {
        "contact_count": len(saved),
        "contacts": [
            {
                "id": c.id,
                "full_name": c.full_name,
                "title": c.title,
                "email": c.email,
                "linkedin_url": c.linkedin_url,
                "priority_rank": c.priority_rank,
                "priority_reason": c.priority_reason,
            }
            for c in saved
        ],
        "pipeline_stage": "contacts_persisted",
        "stages_completed": ["persist_contacts"],
        **progress_entry(f"Saved {len(saved)} contact(s) to database"),
    }


def prepare_outreach_node(state: OpenRoleState) -> dict:
    """Load top contact IDs for parallel research/draft workers."""
    job_id = state.get("job_id")
    if not job_id:
        return {"errors": ["job_id required for outreach prep"]}

    opts = PipelineOptions.from_state(state.get("pipeline_options"))
    with session_scope() as session:
        job = session.scalar(select(Job).where(Job.id == job_id).limit(1))
        if job is None or not job.company_id:
            return {"errors": ["Job not found for outreach prep"]}
        contacts = dedupe_contacts_for_research(
            list_contacts_for_job(
                session,
                company_id=job.company_id,
                source_job_id=job_id,
            )[: opts.research_limit * 2]
        )[: opts.research_limit]

    if not contacts:
        return {
            "contact_ids": [],
            "errors": ["No contacts for this job — run people discovery first"],
            "pipeline_stage": "outreach_prep_empty",
        }

    return {
        "contact_ids": [c.id for c in contacts],
        "pipeline_stage": "outreach_prepared",
        "stages_completed": ["prepare_outreach"],
    }
