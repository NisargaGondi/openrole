"""Network API loads contacts/drafts by company, not recent-job window."""

from pathlib import Path

from openrole.db.models import (
    Company,
    Contact,
    Job,
    JobStatus,
)
from openrole.db.repository import (
    list_companies_for_network,
    list_contacts_for_company_network,
    list_outreach_drafts_for_company,
    save_outreach_draft,
)
from openrole.db.session import init_db, session_scope


def _reset_db(monkeypatch, db_path: Path) -> None:
    url = "sqlite:///" + str(db_path.resolve())
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setattr("openrole.config.load_dotenv", lambda *_a, **_k: None)
    import openrole.db.session as db_session
    from openrole.config import clear_settings_cache

    db_session._engine = None
    db_session._SessionLocal = None
    clear_settings_cache()
    init_db()


def test_network_company_includes_all_contacts_and_drafts(monkeypatch, tmp_path):
    _reset_db(monkeypatch, tmp_path / "network_test.db")

    with session_scope() as session:
        company = Company(name="Pipeline Co", domain="pipeline.co")
        session.add(company)
        session.flush()

        job = Job(
            title="Old ML Role",
            company_id=company.id,
            status=JobStatus.REVIEWING,
            source_url="https://example.com/old",
        )
        session.add(job)
        session.flush()

        contact = Contact(
            company_id=company.id,
            full_name="Alex Recruiter",
            title="Engineering Manager",
            metadata_json={"source_job_id": job.id},
        )
        session.add(contact)
        session.flush()

        save_outreach_draft(
            session,
            contact_id=contact.id,
            job_id=job.id,
            channel="email",
            subject="Hello",
            body="Draft body for old pipeline job.",
        )

        companies = list_companies_for_network(session)
        assert len(companies) == 1
        cid = companies[0].id
        contacts = list_contacts_for_company_network(session, cid)
        drafts = list_outreach_drafts_for_company(session, cid)
        assert len(contacts) == 1
        assert len(drafts) == 1
        assert drafts[0].body.startswith("Draft body")


def test_network_includes_companies_with_jobs_but_no_contacts(monkeypatch, tmp_path):
    _reset_db(monkeypatch, tmp_path / "network_jobs_only.db")

    with session_scope() as session:
        company = Company(name="Real Corp", domain="realcorp.com")
        session.add(company)
        session.flush()
        session.add(
            Job(
                title="ML Engineer",
                company_id=company.id,
                status=JobStatus.DISCOVERED,
                source_url="https://boards.greenhouse.io/realcorp/jobs/1",
            )
        )
        session.flush()

        companies = list_companies_for_network(session)
        assert len(companies) == 1
        assert companies[0].name == "Real Corp"
        assert list_contacts_for_company_network(session, company.id) == []
