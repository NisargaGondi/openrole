"""Persist parsed jobs and companies."""

from __future__ import annotations

from datetime import datetime, timezone
import uuid

from sqlalchemy import or_, select
from sqlalchemy.orm import joinedload

from openrole.db.models import Application, Company, Contact, Job, JobStatus, Outreach, OutreachChannel, OutreachStatus, Resume
from openrole.db.session import session_scope
from openrole.schemas.job import ParsedJob
from openrole.util.json_safe import json_safe_dict


def upsert_company(
    session,
    *,
    name: str,
    domain: str | None = None,
) -> Company:
    company: Company | None = None
    if domain:
        company = session.scalar(select(Company).where(Company.domain == domain).limit(1))
    if company is None:
        company = session.scalar(
            select(Company).where(Company.name == name).limit(1)
        )
    if company is None:
        company = Company(name=name, domain=domain)
        session.add(company)
        session.flush()
    else:
        if domain and not company.domain:
            company.domain = domain
    return company


def save_parsed_job(parsed: ParsedJob) -> tuple[Job, Company]:
    with session_scope() as session:
        company = upsert_company(
            session,
            name=parsed.company_name,
            domain=parsed.company_domain,
        )
        existing: Job | None = None
        if parsed.source_url:
            existing = session.scalar(
                select(Job).where(Job.source_url == parsed.source_url).limit(1)
            )
        if existing:
            _apply_parsed_to_job(existing, parsed, company.id)
            job = existing
        else:
            job = Job(
                company_id=company.id,
                status=JobStatus.DISCOVERED,
                **_sanitize_job_db_dict(parsed.to_db_dict()),
            )
            session.add(job)
            session.flush()
        session.refresh(job)
        session.refresh(company)
        return job, company


def save_discovered_contacts(
    session,
    *,
    company_id: str,
    contacts: list,
    source_job_id: str,
) -> list[Contact]:
    """Upsert ranked contacts for a company (from people discovery)."""
    from openrole.schemas.contact import DiscoveredContact

    discovery_run_id = str(uuid.uuid4())
    saved: list[Contact] = []
    for item in contacts:
        if not isinstance(item, DiscoveredContact):
            raise TypeError("contacts must be DiscoveredContact instances")
        payload = item.to_db_dict(company_id=company_id, source_job_id=source_job_id)
        meta = payload.get("metadata_json") or {}
        meta["discovery_run_id"] = discovery_run_id
        meta["latest_discovery_run_id"] = discovery_run_id
        meta["discovered_at"] = datetime.now(timezone.utc).isoformat()
        meta["stale_for_job"] = False
        payload["metadata_json"] = meta
        apollo_id = (payload.get("metadata_json") or {}).get("apollo_person_id")
        careershift_id = (payload.get("metadata_json") or {}).get("careershift_contact_id")
        existing = _find_existing_contact(
            session,
            company_id=company_id,
            apollo_id=apollo_id,
            careershift_id=careershift_id,
            linkedin_url=payload.get("linkedin_url"),
            email=payload.get("email"),
        )
        if existing is None:
            existing = Contact(**payload)
            session.add(existing)
        else:
            for key, value in payload.items():
                if key == "metadata_json" and value:
                    from openrole.schemas.contact import compute_discovery_source

                    merged = {**(existing.metadata_json or {}), **value}
                    merged["discovery_source"] = compute_discovery_source(merged)
                    existing.metadata_json = merged
                elif value is not None:
                    setattr(existing, key, value)
        session.flush()
        session.refresh(existing)
        saved.append(existing)

    mark_stale_contacts_for_job(
        session, company_id=company_id, source_job_id=source_job_id, current_run_id=discovery_run_id
    )
    return saved


def mark_stale_contacts_for_job(session, *, company_id: str, source_job_id: str, current_run_id: str) -> None:
    """Mark older contacts from the same job as stale."""
    rows = session.scalars(
        select(Contact).where(Contact.company_id == company_id)
    ).all()
    for contact in rows:
        meta = dict(contact.metadata_json or {})
        if meta.get("source_job_id") != source_job_id:
            continue
        if meta.get("discovery_run_id") == current_run_id:
            meta["stale_for_job"] = False
        else:
            meta["stale_for_job"] = True
        contact.metadata_json = meta


def list_contacts_for_job(
    session,
    *,
    company_id: str,
    source_job_id: str | None = None,
    include_stale: bool = False,
    include_all_company: bool = False,
) -> list[Contact]:
    rows = list(
        session.scalars(
            select(Contact)
            .where(Contact.company_id == company_id)
            .order_by(Contact.priority_rank.asc(), Contact.full_name.asc())
        )
    )
    if include_all_company or not source_job_id:
        return rows
    filtered: list[Contact] = []
    for contact in rows:
        meta = contact.metadata_json or {}
        if meta.get("source_job_id") != source_job_id:
            continue
        if not include_stale and meta.get("stale_for_job"):
            continue
        filtered.append(contact)
    return filtered


def list_companies_for_network(session, *, limit: int = 500) -> list[Company]:
    """Companies with visible jobs, contacts, and/or outreach drafts."""
    from openrole.agents.scout_rotation import is_junk_scout_company

    company_ids: set[str] = set()

    for job in session.scalars(select(Job).where(Job.company_id.isnot(None))):
        if job.company_id and job_is_ui_visible(job):
            company_ids.add(job.company_id)

    for row in session.execute(
        select(Contact.company_id).where(Contact.company_id.isnot(None)).distinct()
    ):
        if row[0]:
            company_ids.add(row[0])

    for row in session.execute(
        select(Contact.company_id)
        .join(Outreach, Outreach.contact_id == Contact.id)
        .where(Contact.company_id.isnot(None))
        .distinct()
    ):
        if row[0]:
            company_ids.add(row[0])

    for row in session.execute(
        select(Job.company_id)
        .join(Outreach, Outreach.job_id == Job.id)
        .where(Job.company_id.isnot(None))
        .distinct()
    ):
        if row[0]:
            company_ids.add(row[0])

    if not company_ids:
        return []

    cap = max(1, min(limit, 2000))
    companies = list(
        session.scalars(
            select(Company)
            .where(Company.id.in_(company_ids))
            .order_by(Company.name.asc())
            .limit(cap * 2)
        )
    )
    out = [c for c in companies if not is_junk_scout_company(c)]
    return out[:cap]


def list_contacts_for_company_network(session, company_id: str) -> list[Contact]:
    """All contacts at a company for the Network tab (includes stale / other jobs)."""
    return list_contacts_for_job(session, company_id=company_id, include_all_company=True)


def list_outreach_drafts_for_company(session, company_id: str) -> list[Outreach]:
    """All outreach drafts tied to a company via contact or job."""
    contact_ids = select(Contact.id).where(Contact.company_id == company_id)
    job_ids = select(Job.id).where(Job.company_id == company_id)
    return list(
        session.scalars(
            select(Outreach)
            .where(
                or_(
                    Outreach.contact_id.in_(contact_ids),
                    Outreach.job_id.in_(job_ids),
                )
            )
            .order_by(Outreach.created_at.desc())
        )
    )


def list_visible_jobs_for_company(session, company_id: str, *, limit: int = 100) -> list[Job]:
    rows = list(
        session.scalars(
            select(Job)
            .where(Job.company_id == company_id)
            .order_by(Job.updated_at.desc(), Job.created_at.desc())
            .limit(max(limit, 1) * 3)
        )
    )
    visible = [job for job in rows if job_is_ui_visible(job)]
    return visible[:limit]


def delete_junk_scout_companies(session) -> dict[str, int]:
    """Remove test placeholder companies (Acme, etc.) with no real visible jobs."""
    from sqlalchemy import delete

    from openrole.agents.scout_rotation import is_junk_scout_company

    deleted_companies = 0
    deleted_contacts = 0
    deleted_outreach = 0
    deleted_jobs = 0

    for company in list(session.scalars(select(Company))):
        if not is_junk_scout_company(company):
            continue
        jobs = list(session.scalars(select(Job).where(Job.company_id == company.id)))
        if any(job_is_ui_visible(j) for j in jobs):
            continue

        contact_ids = list(
            session.scalars(select(Contact.id).where(Contact.company_id == company.id))
        )
        if contact_ids:
            deleted_outreach += (
                session.execute(delete(Outreach).where(Outreach.contact_id.in_(contact_ids))).rowcount
                or 0
            )
            deleted_contacts += (
                session.execute(delete(Contact).where(Contact.id.in_(contact_ids))).rowcount or 0
            )

        job_ids = [j.id for j in jobs]
        if job_ids:
            deleted_outreach += (
                session.execute(delete(Outreach).where(Outreach.job_id.in_(job_ids))).rowcount or 0
            )
            deleted_jobs += session.execute(delete(Job).where(Job.id.in_(job_ids))).rowcount or 0

        session.delete(company)
        deleted_companies += 1

    session.flush()
    return {
        "companies": deleted_companies,
        "contacts": deleted_contacts,
        "outreach": deleted_outreach,
        "jobs": deleted_jobs,
    }


def update_company_domain(session, company_id: str, domain: str) -> Company:
    from openrole.tools import apollo_client

    company = session.get(Company, company_id)
    if company is None:
        raise ValueError("Company not found")
    company.domain = apollo_client.normalize_domain(domain)
    session.flush()
    return company


def save_research_brief(session, contact_id: str, brief: dict) -> Contact:
    contact = session.get(Contact, contact_id)
    if contact is None:
        raise ValueError("Contact not found")
    contact.research_brief = brief
    session.flush()
    return contact


def save_outreach_draft(
    session,
    *,
    contact_id: str,
    job_id: str | None,
    channel: str,
    subject: str | None,
    body: str,
) -> Outreach:
    channel_enum = OutreachChannel.LINKEDIN if channel == "linkedin" else OutreachChannel.EMAIL
    existing = session.scalar(
        select(Outreach)
        .where(Outreach.contact_id == contact_id)
        .where(Outreach.job_id == job_id)
        .where(Outreach.channel == channel_enum)
        .where(Outreach.status == OutreachStatus.DRAFT)
        .limit(1)
    )
    if existing:
        existing.subject = subject
        existing.body = body
        existing.validation_notes = {"ai_generated": True, "generator": "openrole-llm"}
        outreach = existing
    else:
        outreach = Outreach(
            contact_id=contact_id,
            job_id=job_id,
            channel=channel_enum,
            subject=subject,
            body=body,
            status=OutreachStatus.DRAFT,
            validation_notes={"ai_generated": True, "generator": "openrole-llm"},
        )
        session.add(outreach)
    session.flush()
    return outreach


def list_outreach_drafts(session, *, job_id: str | None = None, limit: int = 50) -> list[Outreach]:
    q = select(Outreach).order_by(Outreach.created_at.desc()).limit(limit)
    if job_id:
        q = q.where(Outreach.job_id == job_id)
    return list(session.scalars(q))


def sync_resumes_from_env(session) -> list[Resume]:
    """Upsert Resume rows from CANDIDATE_RESUME_PATHS in .env; drop stale DB rows."""
    from openrole.tools.candidate_profile import load_candidate_profile

    profile = load_candidate_profile(fetch_links=False)
    env_items = profile.get("resumes") or []
    env_paths = {item.get("path") for item in env_items if item.get("path")}
    env_labels = {item.get("label") for item in env_items if item.get("label")}

    for row in list(session.scalars(select(Resume))):
        path = row.file_path
        if path and path not in env_paths:
            session.delete(row)
        elif not path and row.label not in env_labels:
            session.delete(row)
    session.flush()

    synced: list[Resume] = []
    for idx, item in enumerate(env_items):
        path = item.get("path")
        label = item.get("label") or f"resume_{idx + 1}"
        text = item.get("text") or ""
        existing: Resume | None = None
        if path:
            existing = session.scalar(select(Resume).where(Resume.file_path == path).limit(1))
        if existing is None:
            existing = session.scalar(select(Resume).where(Resume.label == label).limit(1))
        if existing is None:
            existing = Resume(
                label=label,
                file_path=path,
                content_text=text,
                is_default=False,
            )
            session.add(existing)
        else:
            existing.label = label
            existing.file_path = path
            existing.content_text = text
        session.flush()
        synced.append(existing)

    for row in session.scalars(select(Resume)):
        row.is_default = False
    if synced:
        synced[0].is_default = True
        session.flush()

    return synced


def list_resumes(session) -> list[Resume]:
    return sync_resumes_from_env(session)


def save_job_resume_analysis(session, *, job_id: str, report: dict) -> Job:
    job = session.get(Job, job_id)
    if job is None:
        raise ValueError("Job not found")
    payload = dict(job.raw_payload or {})
    analyses = dict(payload.get("resume_analyses") or {})
    label = report.get("resume_label") or "default"
    analyses[label] = report
    payload["resume_analyses"] = analyses
    payload["resume_report"] = max(
        analyses.values(),
        key=lambda r: int(r.get("match_score") or 0),
    )
    job.raw_payload = payload
    session.flush()
    return job


def best_resume_report(raw_payload: dict | None) -> dict:
    """Primary resume report for API display — highest match_score across variants."""
    payload = raw_payload or {}
    analyses = payload.get("resume_analyses") or {}
    primary = payload.get("resume_report") or {}
    if not analyses:
        return primary if isinstance(primary, dict) else {}
    best = max(analyses.values(), key=lambda r: int(r.get("match_score") or 0))
    if not primary:
        return best
    if int(best.get("match_score") or 0) >= int(primary.get("match_score") or 0):
        return best
    return primary


def save_application_draft(
    session,
    *,
    job_id: str,
    resume_id: str | None,
    answers_json: dict,
) -> Application:
    existing = session.scalar(
        select(Application).where(Application.job_id == job_id).order_by(Application.created_at.desc())
    )
    if existing is None:
        existing = Application(job_id=job_id, resume_id=resume_id, answers_json=answers_json)
        session.add(existing)
    else:
        existing.resume_id = resume_id
        existing.answers_json = answers_json
    session.flush()
    return existing


def get_application_for_job(session, job_id: str) -> Application | None:
    return session.scalar(
        select(Application).where(Application.job_id == job_id).order_by(Application.created_at.desc())
    )


def save_pipeline_run(session, *, job_id: str, run_meta: dict) -> None:
    """Append pipeline run metadata to job.raw_payload (newest first)."""
    job = session.get(Job, job_id)
    if job is None:
        return
    payload = dict(job.raw_payload or {})
    runs = list(payload.get("pipeline_runs") or [])
    runs.insert(0, run_meta)
    payload["pipeline_runs"] = runs[:25]
    job.raw_payload = payload


def get_pipeline_runs(session, job_id: str) -> list[dict]:
    job = session.get(Job, job_id)
    if job is None or not job.raw_payload:
        return []
    return list(job.raw_payload.get("pipeline_runs") or [])


def _find_existing_contact(
    session,
    *,
    company_id: str,
    apollo_id: str | None,
    careershift_id: str | None,
    linkedin_url: str | None,
    email: str | None,
) -> Contact | None:
    candidates = session.scalars(select(Contact).where(Contact.company_id == company_id)).all()
    for contact in candidates:
        meta = contact.metadata_json or {}
        if apollo_id and meta.get("apollo_person_id") == apollo_id:
            return contact
        if careershift_id and meta.get("careershift_contact_id") == careershift_id:
            return contact
        if linkedin_url and contact.linkedin_url == linkedin_url:
            return contact
        if email and contact.email == email:
            return contact
    return None


def save_scout_discovered_job(
    parsed: ParsedJob,
    *,
    scout_meta: dict[str, Any],
) -> tuple[Job, Company, bool]:
    """Persist a scout hit; merge scout metadata into raw_payload. Returns (job, company, is_new)."""
    from openrole.tools.domain_resolver import enrich_parsed_job_domain

    parsed, domain_warnings = enrich_parsed_job_domain(parsed)
    scout_meta = dict(scout_meta)
    if domain_warnings:
        scout_meta["domain_warnings"] = domain_warnings

    with session_scope() as session:
        company = upsert_company(
            session,
            name=parsed.company_name,
            domain=parsed.company_domain,
        )
        existing: Job | None = None
        if parsed.source_url:
            existing = session.scalar(
                select(Job).where(Job.source_url == parsed.source_url).limit(1)
            )
        is_new = existing is None
        if existing:
            _apply_parsed_to_job(existing, parsed, company.id)
            payload = json_safe_dict(dict(existing.raw_payload or {}))
            scout = dict((payload or {}).get("scout") or {})
            scout.update(scout_meta)
            payload = dict(payload or {})
            payload["scout"] = scout
            existing.raw_payload = payload
            job = existing
        else:
            payload = json_safe_dict(dict(parsed.raw_payload or {}))
            payload = dict(payload or {})
            payload["scout"] = scout_meta
            db = _sanitize_job_db_dict(parsed.to_db_dict())
            db["raw_payload"] = payload
            job = Job(company_id=company.id, status=JobStatus.DISCOVERED, **db)
            session.add(job)
            session.flush()
        session.refresh(job)
        session.refresh(company)
        return job, company, is_new


def list_companies_with_scout_metadata(session, *, limit: int = 200) -> list[Company]:
    """Companies that may have ATS tokens or careers URLs in metadata_json."""
    return list(session.scalars(select(Company).order_by(Company.name.asc()).limit(limit)))


def job_hints_for_url(source_url: str) -> tuple[str | None, str | None]:
    """Return (title, company_name) for a known job URL — helps Indeed re-ingest."""
    from openrole.db.models import Company

    with session_scope() as session:
        job = session.scalar(select(Job).where(Job.source_url == source_url).limit(1))
        if job is None:
            return None, None
        company = session.get(Company, job.company_id)
        return job.title, company.name if company else None


def load_known_job_urls(session) -> set[str]:
    """URLs already in the jobs table — skip re-filtering on repeat scout runs."""
    known: set[str] = set()
    for source_url, apply_url in session.execute(select(Job.source_url, Job.apply_url)):
        for url in (source_url, apply_url):
            if url:
                known.add(url.strip())
    return known


def job_is_ui_visible(job: Job) -> bool:
    return not bool((job.raw_payload or {}).get("ui_hidden"))


def list_jobs_for_tracker(
    session,
    *,
    status: str | None = None,
    limit: int = 100,
    include_hidden: bool = False,
) -> list[Job]:
    q = (
        select(Job)
        .options(joinedload(Job.company))
        .order_by(Job.updated_at.desc(), Job.created_at.desc())
        .limit(limit if include_hidden else limit * 3)
    )
    if status and status != "all":
        try:
            q = q.where(Job.status == JobStatus(status))
        except ValueError:
            pass
    rows = list(session.scalars(q).unique())
    if include_hidden:
        return rows[:limit]
    visible = [j for j in rows if job_is_ui_visible(j)]
    return visible[:limit]


def get_job_with_company(session, job_id: str) -> Job | None:
    return session.scalar(
        select(Job).options(joinedload(Job.company)).where(Job.id == job_id).limit(1)
    )


def list_jobs_for_workflow(session, *, limit: int = 300) -> list[Job]:
    """Same ordering as dashboard tracker — keeps pipeline job picker in sync."""
    return list_jobs_for_tracker(session, status="all", limit=limit)


def delete_contact(session, contact_id: str) -> bool:
    """Delete one contact and its outreach drafts. Returns False if not found."""
    from sqlalchemy import delete

    contact = session.get(Contact, contact_id)
    if contact is None:
        return False
    session.execute(delete(Outreach).where(Outreach.contact_id == contact_id))
    session.delete(contact)
    session.flush()
    return True


def apply_careershift_email(
    session,
    contact_id: str,
    *,
    email: str,
    fields: dict[str, Any] | None = None,
) -> Contact | None:
    """Persist email fetched from CareerShift detail panel."""
    from openrole.scrapers.email_utils import clean_email

    contact = session.get(Contact, contact_id)
    if contact is None:
        return None
    cleaned = clean_email(email)
    if not cleaned:
        return None
    contact.email = cleaned
    meta = dict(contact.metadata_json or {})
    meta["careershift_search"] = True
    meta["needs_email"] = False
    meta["email_actionable"] = True
    meta.pop("email_ai_generated", None)
    meta.pop("email_guess_confidence", None)
    meta.pop("email_guess_pattern", None)
    if fields:
        cs_id = fields.get("careershift_id")
        if cs_id:
            meta["careershift_contact_id"] = cs_id
        if fields.get("location") and not contact.location:
            contact.location = fields["location"]
        if fields.get("title") and not contact.title:
            contact.title = fields["title"]
    meta["careershift_email_fetched_at"] = datetime.now(timezone.utc).isoformat()
    contact.metadata_json = meta
    session.flush()
    return contact


def delete_job(session, job_id: str) -> bool:
    """Delete one job and its outreach/applications. Returns False if not found."""
    from sqlalchemy import delete

    job = session.get(Job, job_id)
    if job is None:
        return False
    session.execute(delete(Outreach).where(Outreach.job_id == job_id))
    session.execute(delete(Application).where(Application.job_id == job_id))
    session.delete(job)
    session.flush()
    return True


def delete_all_jobs(session) -> dict[str, int]:
    """Remove all jobs and related outreach/applications (fresh testing reset)."""
    from sqlalchemy import delete

    outreach_deleted = session.execute(delete(Outreach)).rowcount or 0
    apps_deleted = session.execute(delete(Application)).rowcount or 0
    jobs_deleted = session.execute(delete(Job)).rowcount or 0
    return {
        "outreach": outreach_deleted,
        "applications": apps_deleted,
        "jobs": jobs_deleted,
    }


def update_job_status(session, job_id: str, status: JobStatus | str) -> Job:
    job = session.get(Job, job_id)
    if job is None:
        raise ValueError("Job not found")
    if isinstance(status, str):
        status = JobStatus(status)
    job.status = status
    session.flush()
    return job


def set_job_notion_page_id(session, job_id: str, page_id: str) -> None:
    job = session.get(Job, job_id)
    if job is None:
        return
    payload = dict(job.raw_payload or {})
    sync_meta = dict(payload.get("sync") or {})
    sync_meta["notion_page_id"] = page_id
    payload["sync"] = sync_meta
    job.raw_payload = payload
    session.flush()


def get_job_notion_page_id(job: Job) -> str | None:
    sync_meta = (job.raw_payload or {}).get("sync") or {}
    page_id = sync_meta.get("notion_page_id")
    return str(page_id) if page_id else None


def list_jobs_for_scout_sync(session, *, since_scout_run: str | None = None, limit: int = 100) -> list[Job]:
    """Jobs with scout metadata, newest first."""
    rows = list(
        session.scalars(
            select(Job)
            .options(joinedload(Job.company))
            .order_by(Job.created_at.desc())
            .limit(limit)
        ).unique()
    )
    if not since_scout_run:
        return [j for j in rows if (j.raw_payload or {}).get("scout")]
    return [
        j
        for j in rows
        if ((j.raw_payload or {}).get("scout") or {}).get("run_id") == since_scout_run
    ]


def count_contacts_for_jobs(session, job_ids: set[str] | frozenset[str]) -> int:
    """Contacts discovered for specific job(s) — matches Network / job detail views."""
    if not job_ids:
        return 0
    rows = list(session.scalars(select(Contact)))
    n = 0
    for contact in rows:
        meta = contact.metadata_json or {}
        if meta.get("source_job_id") in job_ids and not meta.get("stale_for_job"):
            n += 1
    return n


def get_dashboard_stats() -> dict[str, Any]:
    """Aggregate counts for the home dashboard."""
    from sqlalchemy import func, select

    with session_scope() as session:
        all_jobs = list(session.scalars(select(Job)))
        visible_jobs = [j for j in all_jobs if job_is_ui_visible(j)]
        jobs_by_status: dict[str, int] = {}
        for j in visible_jobs:
            key = j.status.value if hasattr(j.status, "value") else str(j.status)
            jobs_by_status[key] = jobs_by_status.get(key, 0) + 1
        total_jobs = len(visible_jobs)
        scout_jobs = sum(1 for j in visible_jobs if (j.raw_payload or {}).get("scout"))
        visible_job_ids = {j.id for j in visible_jobs}
        if visible_job_ids:
            pending_outreach = (
                session.scalar(
                    select(func.count())
                    .select_from(Outreach)
                    .where(Outreach.status == OutreachStatus.DRAFT)
                    .where(Outreach.job_id.in_(visible_job_ids))
                )
                or 0
            )
        else:
            pending_outreach = 0
        visible_company_ids = {j.company_id for j in visible_jobs if j.company_id}
        total_contacts = count_contacts_for_jobs(session, visible_job_ids)
        companies = (
            list(session.scalars(select(Company).where(Company.id.in_(visible_company_ids))))
            if visible_company_ids
            else []
        )
        companies_with_scout = sum(
            1
            for c in companies
            if (c.metadata_json or {}).get("greenhouse_token")
            or (c.metadata_json or {}).get("lever_slug")
            or (c.metadata_json or {}).get("ashby_org")
            or (c.metadata_json or {}).get("careers_url")
        )

    return {
        "total_jobs": total_jobs,
        "jobs_by_status": jobs_by_status,
        "scout_jobs": scout_jobs,
        "pending_outreach": pending_outreach,
        "total_contacts": total_contacts,
        "companies_total": len(companies),
        "companies_with_scout_metadata": companies_with_scout,
    }


def _sanitize_job_db_dict(db: dict[str, Any]) -> dict[str, Any]:
    out = dict(db)
    if out.get("raw_payload") is not None:
        out["raw_payload"] = json_safe_dict(out["raw_payload"])
    return out


def _apply_parsed_to_job(job: Job, parsed: ParsedJob, company_id: str) -> None:
    job.company_id = company_id
    for key, value in _sanitize_job_db_dict(parsed.to_db_dict()).items():
        setattr(job, key, value)
