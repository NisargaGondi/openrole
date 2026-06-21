"""Tests for single job deletion."""

from openrole.db.models import Company, Job, JobStatus
from openrole.db.repository import delete_job, list_jobs_for_tracker
from openrole.db.session import init_db, session_scope


def test_delete_job_removes_row(monkeypatch):
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
            source_url="https://example.com/job/1",
        )
        session.add(job)
        session.flush()
        job_id = job.id

    with session_scope() as session:
        assert delete_job(session, job_id) is True

    with session_scope() as session:
        assert list_jobs_for_tracker(session) == []

    with session_scope() as session:
        assert delete_job(session, "missing-id") is False
