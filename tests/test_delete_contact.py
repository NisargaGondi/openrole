"""Tests for single contact deletion."""

from openrole.db.models import Company, Contact, Job, JobStatus, Outreach, OutreachChannel, OutreachStatus
from openrole.db.repository import delete_contact, list_contacts_for_job
from openrole.db.session import init_db, session_scope


def test_delete_contact_removes_row(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    import openrole.db.session as db_session
    from openrole.config import get_settings

    db_session._engine = None
    db_session._SessionLocal = None
    get_settings.cache_clear()
    init_db()

    with session_scope() as session:
        company = Company(name="Acme", domain="acme.com")
        session.add(company)
        session.flush()
        job = Job(
            company_id=company.id,
            title="Engineer",
            status=JobStatus.DISCOVERED,
        )
        session.add(job)
        session.flush()
        contact = Contact(
            company_id=company.id,
            full_name="Jane Doe",
            title="Engineering Manager",
            metadata_json={"source_job_id": job.id},
        )
        session.add(contact)
        session.flush()
        outreach = Outreach(
            contact_id=contact.id,
            job_id=job.id,
            channel=OutreachChannel.EMAIL,
            body="Hello",
            status=OutreachStatus.DRAFT,
        )
        session.add(outreach)
        session.flush()
        contact_id = contact.id
        job_id = job.id
        company_id = company.id

    with session_scope() as session:
        assert delete_contact(session, contact_id) is True

    with session_scope() as session:
        assert list_contacts_for_job(session, company_id=company_id, source_job_id=job_id) == []

    with session_scope() as session:
        assert delete_contact(session, "missing") is False
