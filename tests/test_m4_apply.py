"""Tests for resume optimizer and application assistant."""

from unittest.mock import MagicMock, patch

import openrole.db.session as db_session
import pytest
from openrole.agents.app_assistant import draft_application_answers
from openrole.agents.resume_optimizer import ResumeOptimizerError, optimize_resume_for_job
from openrole.config import get_settings
from openrole.db.models import Company, Job
from openrole.db.session import init_db, session_scope


def _seed_job_with_description(tmp_path, monkeypatch):
    db_session._engine = None
    db_session._SessionLocal = None
    get_settings.cache_clear()
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")

    resume = tmp_path / "resume.md"
    resume.write_text(
        "Jane Doe\nCMU MS ML\nSkills: Python, PyTorch, distributed systems\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CANDIDATE_RESUME_PATHS", str(resume))
    monkeypatch.setenv("CANDIDATE_NAME", "Jane Doe")
    get_settings.cache_clear()
    init_db()

    with session_scope() as session:
        co = Company(name="Acme", domain="acme.com")
        session.add(co)
        session.flush()
        job = Job(
            company_id=co.id,
            title="ML Engineer",
            description="Looking for Python, PyTorch, and Kubernetes experience.",
        )
        session.add(job)
        session.commit()
        return job.id


@patch("openrole.agents.resume_optimizer.get_chat_model")
def test_optimize_resume_for_job(mock_model, tmp_path, monkeypatch):
    job_id = _seed_job_with_description(tmp_path, monkeypatch)
    mock_llm = MagicMock()
    mock_llm.invoke.return_value = MagicMock(
        content="""
        {
          "match_score": 78,
          "summary": "Strong ML background; add Kubernetes keyword.",
          "strengths": ["PyTorch"],
          "gaps": ["Kubernetes"],
          "missing_keywords": ["kubernetes"],
          "ats_risks": [],
          "suggested_edits": [{"section": "Skills", "issue": "missing k8s", "suggestion": "Add Kubernetes"}]
        }
        """
    )
    mock_model.return_value = mock_llm

    out = optimize_resume_for_job(job_id=job_id)
    assert out["report"]["match_score"] == 78
    assert "Kubernetes" in out["report"]["summary"]


@patch("openrole.agents.app_assistant.get_chat_model")
def test_draft_application_answers(mock_model, tmp_path, monkeypatch):
    job_id = _seed_job_with_description(tmp_path, monkeypatch)
    mock_llm = MagicMock()
    mock_llm.invoke.return_value = MagicMock(
        content="""
        {
          "answers": [
            {"question": "Why Acme?", "answer": "I built ML pipelines at CMU.", "notes": null}
          ],
          "tone_notes": "Keep concise"
        }
        """
    )
    mock_model.return_value = mock_llm

    out = draft_application_answers(job_id=job_id, questions=["Why Acme?"])
    assert out["draft"]["answers"][0]["answer"]
    assert "application_id" in out


def test_optimize_requires_description(tmp_path, monkeypatch):
    db_session._engine = None
    db_session._SessionLocal = None
    get_settings.cache_clear()
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    init_db()
    with session_scope() as session:
        co = Company(name="X", domain="x.com")
        session.add(co)
        session.flush()
        job = Job(company_id=co.id, title="Role", description=None)
        session.add(job)
        session.commit()
        jid = job.id
    with pytest.raises(ResumeOptimizerError, match="no description"):
        optimize_resume_for_job(job_id=jid)
