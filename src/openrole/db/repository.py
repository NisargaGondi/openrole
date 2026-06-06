"""Persist parsed jobs and companies."""

from __future__ import annotations

from datetime import datetime, timezone
import uuid

from sqlalchemy import select

from openrole.db.models import Application, Company, Contact, Job, JobStatus, Outreach, OutreachChannel, OutreachStatus, Resume
from openrole.db.session import session_scope
from openrole.schemas.job import ParsedJob


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
            job = Job(company_id=company.id, status=JobStatus.DISCOVERED, **parsed.to_db_dict())
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
        outreach = existing
    else:
        outreach = Outreach(
            contact_id=contact_id,
            job_id=job_id,
            channel=channel_enum,
            subject=subject,
            body=body,
            status=OutreachStatus.DRAFT,
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
    """Upsert Resume rows from CANDIDATE_RESUME_PATHS in .env."""
    from openrole.tools.candidate_profile import load_candidate_profile

    profile = load_candidate_profile(fetch_links=False)
    synced: list[Resume] = []
    for idx, item in enumerate(profile.get("resumes") or []):
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
                is_default=(idx == 0),
            )
            session.add(existing)
        else:
            existing.label = label
            existing.file_path = path
            existing.content_text = text
            if idx == 0:
                existing.is_default = True
        session.flush()
        synced.append(existing)
    return synced


def list_resumes(session) -> list[Resume]:
    rows = list(session.scalars(select(Resume).order_by(Resume.is_default.desc(), Resume.label.asc())))
    if rows:
        return rows
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
    job.raw_payload = payload
    session.flush()
    return job


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


def _apply_parsed_to_job(job: Job, parsed: ParsedJob, company_id: str) -> None:
    job.company_id = company_id
    for key, value in parsed.to_db_dict().items():
        setattr(job, key, value)
