"""M5 LangGraph pipeline: checkpointer, interrupts, Send workers, evaluator loop."""

from unittest.mock import MagicMock, patch

import openrole.db.session as db_session
import pytest
from langgraph.types import Command

from openrole.db.models import Company, Contact, Job
from openrole.db.session import init_db, session_scope
from openrole.graph.main_graph import get_pipeline_graph
from openrole.graph.pipeline_runner import (
    run_pipeline_sync,
    run_pipeline_to_completion,
    run_pipeline_until_pause,
    resume_pipeline,
)
from openrole.schemas.pipeline import PipelineOptions


def _seed_job_with_contact(tmp_path, monkeypatch):
    db_session._engine = None
    db_session._SessionLocal = None
    from openrole.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    resume = tmp_path / "r.md"
    resume.write_text("Jane Doe\nCMU MS ML\nPython PyTorch\n", encoding="utf-8")
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
            description="Python, PyTorch, Kubernetes required.",
        )
        session.add(job)
        session.flush()
        contact = Contact(
            company_id=co.id,
            full_name="Pat Lee",
            title="Engineering Manager",
            email="pat@acme.com",
            priority_rank=1,
            research_brief={"suggested_hook": "ML platform work", "talking_points": ["k8s"]},
            metadata_json={"source_job_id": job.id, "tier": "hiring_manager"},
        )
        session.add(contact)
        session.commit()
        return job.id, contact.id


@patch("openrole.graph.nodes.ingest.ingest_job")
def test_ingest_only_legacy(mock_ingest, tmp_path, monkeypatch):
    mock_ingest.return_value = {
        "job_id": "j1",
        "company_id": "c1",
        "parsed_job": {"title": "Eng", "company_name": "X"},
        "warnings": [],
    }
    out = run_pipeline_sync(job_text="hello", use_legacy_ingest_only=True)
    assert out["job_id"] == "j1"


@patch("openrole.graph.nodes.outreach.draft_outreach_optimized")
@patch("openrole.graph.nodes.outreach.research_contact_for_job")
def test_pipeline_interrupts_at_outreach_review(mock_research, mock_draft, tmp_path, monkeypatch):
    job_id, contact_id = _seed_job_with_contact(tmp_path, monkeypatch)
    mock_research.return_value = {"status": "ok", "brief": {}}
    mock_draft.return_value = {
        "drafts": [{"id": "d1", "channel": "email"}],
        "evaluation": {
            "acceptable": True,
            "grade": "good",
            "contact_id": contact_id,
            "email_score": 90,
            "linkedin_score": 88,
            "attempts": 1,
        },
        "profile_warnings": [],
    }

    opts = PipelineOptions(
        run_people=False,
        run_research=True,
        run_outreach=True,
        run_resume=False,
        research_limit=1,
    )
    result = run_pipeline_until_pause(job_id=job_id, options=opts)
    assert result.interrupted
    assert result.thread_id
    gate = getattr(result.interrupts[0], "value", None) or result.interrupts[0]
    if isinstance(gate, dict):
        assert gate.get("gate") == "outreach_review"

    completed = resume_pipeline(result.thread_id, approved=False)
    assert completed.state.get("pipeline_stage") == "complete" or not completed.interrupted


def test_graph_compiles():
    app = get_pipeline_graph()
    assert app is not None


@patch("openrole.graph.nodes.outreach.draft_outreach_optimized")
@patch("openrole.graph.nodes.outreach.research_contact_for_job")
def test_evaluator_optimizer_called_in_worker(mock_res, mock_draft, tmp_path, monkeypatch):
    job_id, contact_id = _seed_job_with_contact(tmp_path, monkeypatch)
    mock_draft.return_value = {
        "drafts": [{"id": "d1", "channel": "email"}],
        "evaluation": {"acceptable": True, "grade": "good", "attempts": 2},
    }

    from openrole.graph.nodes.outreach import draft_worker_node

    out = draft_worker_node(
        {"job_id": job_id, "contact_id": contact_id, "max_draft_iterations": 3}
    )
    mock_draft.assert_called_once()
    assert mock_draft.call_args.kwargs["max_iterations"] == 3
    assert out.get("draft_evaluations")
