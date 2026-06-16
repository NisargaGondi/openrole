"""Tests for job ingestion (no live network except where mocked)."""

from unittest.mock import patch

import pytest

from openrole.agents.job_ingestion import JobIngestionError, ingest_job
from openrole.db.models import Company, Job
from openrole.db.session import init_db, session_scope
from openrole.schemas.job import ParsedJob
from openrole.scrapers.url_detect import JobPlatform, detect_job_url


def test_detect_greenhouse_url():
    info = detect_job_url("https://boards.greenhouse.io/acme/jobs/123456")
    assert info.platform == JobPlatform.GREENHOUSE
    assert info.board_token == "acme"
    assert info.job_id == "123456"


def test_detect_lever_url():
    info = detect_job_url("https://jobs.lever.co/acme/abc-123-def")
    assert info.platform == JobPlatform.LEVER
    assert info.company_slug == "acme"
    assert info.job_id == "abc-123-def"


def test_heuristic_text_ingest(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    import openrole.db.session as db_session
    from openrole.config import get_settings

    db_session._engine = None
    db_session._SessionLocal = None
    get_settings.cache_clear()

    monkeypatch.setattr(
        "openrole.agents.job_ingestion.get_settings",
        lambda: type("S", (), {"llm_configured": False})(),
    )

    init_db()
    result = ingest_job(
        job_text="ML Engineer\nCompany: Acme AI\nBuild models for security products."
    )
    assert result["job_id"]
    assert result["parsed_job"]["title"] == "ML Engineer"
    assert result["parsed_job"]["company_name"] == "Acme AI"


@patch("openrole.scrapers.ats_apis._get_json")
def test_greenhouse_ingest(mock_get_json, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    import openrole.db.session as db_session
    from openrole.config import get_settings

    db_session._engine = None
    db_session._SessionLocal = None
    get_settings.cache_clear()
    init_db()

    mock_get_json.return_value = {
        "id": 123456,
        "title": "Security Engineer",
        "content": "<p>Build secure systems</p>",
        "location": {"name": "Pittsburgh, PA"},
        "departments": [{"name": "Security"}],
        "absolute_url": "https://boards.greenhouse.io/acme/jobs/123456",
    }

    result = ingest_job(job_url="https://boards.greenhouse.io/acme/jobs/123456")
    assert result["parsed_job"]["title"] == "Security Engineer"
    assert result["parsed_job"]["source_platform"] == "greenhouse"

    with session_scope() as session:
        job = session.get(Job, result["job_id"])
        assert job is not None
        assert job.department == "Security"
        company = session.get(Company, result["company_id"])
        assert company is not None


def test_workday_requires_text():
    with pytest.raises(JobIngestionError):
        ingest_job(job_url="https://acme.wd5.myworkdayjobs.com/en-US/careers/jobs")
