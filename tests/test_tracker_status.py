"""Tests for job tracker status updates."""

import openrole.db.session as db_session
from openrole.config import clear_settings_cache
from openrole.db.models import Job, JobStatus
from openrole.db.repository import list_jobs_for_tracker, update_job_status
from openrole.db.session import init_db, session_scope
from openrole.schemas.job import ParsedJob
from openrole.db.repository import save_parsed_job


def test_update_job_status(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'tracker.db'}")
    clear_settings_cache()
    db_session._engine = None
    db_session._SessionLocal = None
    init_db()

    parsed = ParsedJob(
        title="ML Engineer",
        company_name="Acme",
        description="PyTorch",
        source_url="https://example.com/ml",
    )
    job, _ = save_parsed_job(parsed)

    with session_scope() as session:
        updated = update_job_status(session, job.id, JobStatus.APPLIED)
        assert updated.status == JobStatus.APPLIED
        rows = list_jobs_for_tracker(session, status="applied")
        assert len(rows) == 1
        assert rows[0].title == "ML Engineer"
