"""Tests for Workday ingestion and JobSpy helpers."""

from unittest.mock import patch

import pytest

from openrole.agents.job_ingestion import JobIngestionError, ingest_job
from openrole.scrapers.url_detect import JobPlatform, detect_job_url
from openrole.scrapers.workday import WorkdayParseError, _parse_workday_url
from openrole.tools import jobspy_client


def test_parse_workday_url():
    host, tenant, site, path = _parse_workday_url(
        "https://cmu.wd5.myworkdayjobs.com/en-US/CMU/job/Pittsburgh-PA/Role_123"
    )
    assert tenant == "cmu"
    assert site == "CMU"
    assert path.startswith("job/")


def test_detect_workday():
    info = detect_job_url("https://cmu.wd5.myworkdayjobs.com/en-US/CMU/job/x/y_z")
    assert info.platform == JobPlatform.WORKDAY


@patch("openrole.scrapers.workday.httpx.Client")
def test_workday_ingest(mock_client_cls, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    import openrole.db.session as db_session
    from openrole.config import get_settings

    db_session._engine = None
    db_session._SessionLocal = None
    get_settings.cache_clear()

    from openrole.db.session import init_db

    init_db()

    mock_response = mock_client_cls.return_value.__enter__.return_value.get.return_value
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "jobPostingInfo": {
            "title": "ML Engineer",
            "location": "Remote",
            "jobDescription": "<p>Build models</p>",
            "externalUrl": "https://cmu.wd5.myworkdayjobs.com/CMU/job/x/y",
        },
        "hiringOrganization": {"name": "Carnegie Mellon University"},
    }

    url = "https://cmu.wd5.myworkdayjobs.com/en-US/CMU/job/Remote/ML-Engineer_1"
    result = ingest_job(job_url=url)
    assert result["parsed_job"]["title"] == "ML Engineer"
    assert result["parsed_job"]["source_platform"] == "workday"


def test_workday_board_url_requires_job_path():
    with pytest.raises(WorkdayParseError):
        _parse_workday_url("https://cmu.wd5.myworkdayjobs.com/en-US/CMU/jobs")


def test_jobspy_probe_without_install(monkeypatch):
    monkeypatch.setattr(jobspy_client, "is_available", lambda: False)
    out = jobspy_client.probe_jobspy()
    assert out["ok"] is False
