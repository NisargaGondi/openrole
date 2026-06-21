"""Tests for Job Scout agent (mocked discovery)."""

import pytest
from unittest.mock import patch

import openrole.db.session as db_session
from openrole.agents.job_scout import run_job_scout
from openrole.agents.resume_scout_profile import build_scout_resume_profile
from openrole.config import clear_settings_cache
from openrole.schemas.job import ParsedJob


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'scout.db'}")
    clear_settings_cache()
    db_session._engine = None
    db_session._SessionLocal = None
    from openrole.db.migrate import main as migrate

    migrate()
    yield tmp_path


def _scout_profile(text: str, label: str = "ml.pdf") -> dict:
    scout = build_scout_resume_profile(text=text, label=label)
    return {
        "resumes": [{"label": label, "text": text}],
        "scout_resume_profile": scout,
        "selected_resume_label": label,
        "role_search": "machine learning engineer",
    }


def _sample_job(title: str = "ML Engineer", desc: str | None = None) -> ParsedJob:
    description = desc or (
        "PyTorch machine learning and LLM inference. "
        "STEM OPT and visa sponsorship available for F-1 students."
    )
    return ParsedJob(
        title=title,
        company_name="Acme",
        description=description,
        source_url=f"https://example.com/jobs/{title.replace(' ', '-').lower()}",
        source_platform="indeed",
    )


from openrole.agents.scout_job_prepare import ScoutBatchPrepareResult


def _mock_batch_prepare(pending, **kwargs):
    prepared = [
        (item.parsed, [], item.source, item.search_term) for item in pending
    ]
    return ScoutBatchPrepareResult(prepared=prepared, llm_jobs=0, llm_batches=0)


@patch("openrole.agents.job_scout.batch_prepare_scout_jobs")
@patch("openrole.agents.job_scout.jobspy_client.search_jobs")
@patch("openrole.agents.job_scout.load_scout_context")
@patch("openrole.agents.job_scout.load_known_job_urls")
def test_scout_skips_known_urls(mock_known, mock_context, mock_search, mock_batch, isolated_db):
    mock_batch.side_effect = _mock_batch_prepare
    mock_known.return_value = {"https://example.com/jobs/machine-learning-engineer"}
    mock_context.return_value = _scout_profile(
        "Machine Learning Engineer. PyTorch, deep learning, NLP, LLM."
    )
    mock_search.return_value = [
        _sample_job("Machine Learning Engineer"),
    ]

    report = run_job_scout(
        search_terms=["machine learning engineer"],
        min_score=0,
        include_ats_boards=False,
        include_handshake=False,
        include_tavily=False,
        sync_notion=False,
        sync_sheets=False,
        require_opt_mention=False,
    )
    assert report.skipped_already_seen == 1
    assert report.ingested_new == 0


@patch("openrole.agents.job_scout.batch_prepare_scout_jobs")
@patch("openrole.agents.job_scout.jobspy_client.search_jobs")
@patch("openrole.agents.job_scout.load_scout_context")
def test_scout_ingests_above_threshold(mock_context, mock_search, mock_batch, isolated_db):
    mock_batch.side_effect = _mock_batch_prepare
    mock_context.return_value = _scout_profile(
        "Machine Learning Engineer. PyTorch, deep learning, NLP, LLM."
    )
    mock_search.return_value = [
        _sample_job("Machine Learning Engineer"),
        _sample_job(
            "Manager, Wealth Operations",
            "Operations role. STEM OPT.",
        ),
    ]

    report = run_job_scout(
        search_terms=["machine learning engineer"],
        min_score=30,
        include_ats_boards=False,
        include_handshake=False,
        include_tavily=False,
        sync_notion=False,
        sync_sheets=False,
        require_opt_mention=False,
    )

    assert report.discovered == 2
    assert report.skipped_not_software >= 1
    assert report.ingested_new + report.updated_existing >= 1
    assert report.top_hits


@patch("openrole.agents.job_scout.batch_prepare_scout_jobs")
@patch("openrole.agents.job_scout.jobspy_client.search_jobs")
@patch("openrole.agents.job_scout.load_scout_context")
def test_scout_syncs_csv_with_detached_jobs(mock_context, mock_search, mock_batch, isolated_db):
    mock_batch.side_effect = _mock_batch_prepare
    mock_context.return_value = _scout_profile(
        "Machine Learning Engineer. PyTorch, deep learning, NLP."
    )
    mock_search.return_value = [_sample_job("Machine Learning Engineer")]

    report = run_job_scout(
        search_terms=["machine learning engineer"],
        min_score=0,
        include_ats_boards=False,
        include_handshake=False,
        include_tavily=False,
        sync_notion=False,
        sync_sheets=True,
        require_opt_mention=False,
    )
    assert report.sheets_synced == 1
    assert report.ingested_new + report.updated_existing == 1


@patch("openrole.agents.job_scout.batch_prepare_scout_jobs")
@patch("openrole.agents.job_scout.jobspy_client.search_jobs")
@patch("openrole.agents.job_scout.load_scout_context")
def test_scout_dry_run_no_persist(mock_context, mock_search, mock_batch, isolated_db):
    mock_batch.side_effect = _mock_batch_prepare
    mock_context.return_value = _scout_profile("Software Engineer. Python, Kubernetes, backend.")
    mock_search.return_value = [
        _sample_job("Software Engineer", "Python Kubernetes distributed systems. STEM OPT.")
    ]

    report = run_job_scout(
        search_terms=["software engineer"],
        min_score=0,
        include_ats_boards=False,
        include_handshake=False,
        include_tavily=False,
        sync_notion=False,
        sync_sheets=False,
        dry_run=True,
        require_opt_mention=False,
    )
    assert report.ingested_new == 1
    assert report.top_hits[0]["job_id"] is None


@patch("openrole.agents.job_scout.batch_prepare_scout_jobs")
@patch("openrole.agents.tavily_job_discovery.discover_jobs_via_tavily")
@patch("openrole.agents.job_scout.jobspy_client.search_jobs")
@patch("openrole.agents.job_scout.load_scout_context")
@patch("openrole.agents.job_scout.load_known_job_urls")
@patch("openrole.tools.web_search.is_configured", return_value=True)
def test_scout_includes_tavily_hits(
    _mock_tavily_cfg,
    mock_known,
    mock_context,
    mock_search,
    mock_tavily,
    mock_batch,
    isolated_db,
):
    mock_batch.side_effect = _mock_batch_prepare
    from openrole.agents.tavily_job_discovery import TavilyJobHit

    mock_known.return_value = set()
    mock_context.return_value = _scout_profile(
        "Machine Learning Engineer. PyTorch, deep learning, NLP, LLM."
    )
    mock_search.return_value = []
    mock_tavily.return_value = (
        [
            TavilyJobHit(
                parsed=_sample_job("ML Engineer — Tavily"),
                source="tavily_ats_boards",
                search_term="machine learning engineer",
                query_type="ats_boards",
            )
        ],
        ["Tavily jobs [ats_boards]: +1"],
    )

    report = run_job_scout(
        search_terms=["machine learning engineer"],
        min_score=30,
        include_ats_boards=False,
        include_handshake=False,
        include_tavily=True,
        sync_notion=False,
        sync_sheets=False,
        require_opt_mention=False,
    )
    assert report.companies_scouted_tavily >= 0
    assert report.discovered >= 1
    assert any(h.get("source", "").startswith("tavily") for h in report.top_hits)
