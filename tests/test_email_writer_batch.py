"""Tests for batch outreach drafting."""

from unittest.mock import MagicMock, patch

import openrole.db.session as db_session
import pytest
from openrole.agents.email_writer import EmailWriterError, draft_outreach_for_job
from openrole.config import get_settings
from openrole.db.models import Company, Contact, Job
from openrole.db.session import init_db, session_scope


def _seed_job_with_contacts(monkeypatch):
    db_session._engine = None
    db_session._SessionLocal = None
    get_settings.cache_clear()
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    init_db()

    with session_scope() as session:
        co = Company(name="Acme", domain="acme.com")
        session.add(co)
        session.flush()
        job = Job(company_id=co.id, title="ML Engineer", description="Build models.")
        session.add(job)
        session.flush()
        c1 = Contact(
            company_id=co.id,
            full_name="Alice Manager",
            title="Engineering Manager",
            metadata_json={"tier": "HIRING_MANAGER", "source_job_id": job.id},
            priority_rank=1,
        )
        c2 = Contact(
            company_id=co.id,
            full_name="Bob Recruiter",
            title="Technical Recruiter",
            metadata_json={"tier": "ROLE_RECRUITER", "source_job_id": job.id},
            priority_rank=2,
            research_brief={"suggested_hook": "hiring ML roles"},
        )
        session.add_all([c1, c2])
        session.commit()
        return job.id, c1.id, c2.id


@patch("openrole.agents.email_writer._generate_drafts")
@patch("openrole.agents.person_research.build_research_brief")
def test_draft_outreach_for_job_all_contacts(mock_brief, mock_generate, monkeypatch):
    job_id, c1_id, c2_id = _seed_job_with_contacts(monkeypatch)
    mock_brief.return_value = MagicMock(to_db_dict=lambda: {"suggested_hook": "team lead"})
    mock_generate.return_value = {
        "email": {"subject": "Hi", "body": "Hello"},
        "linkedin": {"subject": None, "body": "Connect?"},
    }

    out = draft_outreach_for_job(job_id=job_id)

    assert out["contact_count"] == 2
    assert out["drafted_count"] == 2
    assert mock_generate.call_count == 2
    assert mock_brief.call_count == 1


def test_draft_outreach_for_job_no_contacts(monkeypatch):
    db_session._engine = None
    db_session._SessionLocal = None
    get_settings.cache_clear()
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    init_db()

    with session_scope() as session:
        co = Company(name="Acme", domain="acme.com")
        session.add(co)
        session.flush()
        job = Job(company_id=co.id, title="ML Engineer")
        session.add(job)
        session.commit()
        job_id = job.id

    with pytest.raises(EmailWriterError, match="No contacts"):
        draft_outreach_for_job(job_id=job_id)
