"""Persist parsed jobs and companies."""

from __future__ import annotations

from sqlalchemy import select

from openrole.db.models import Company, Job, JobStatus
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


def _apply_parsed_to_job(job: Job, parsed: ParsedJob, company_id: str) -> None:
    job.company_id = company_id
    for key, value in parsed.to_db_dict().items():
        setattr(job, key, value)
