"""Tests for person research (Tavily + Apollo → synthesis brief)."""

from unittest.mock import MagicMock, patch

import openrole.db.session as db_session
import pytest
from openrole.agents.person_research import (
    _clean_synthesis_output,
    _filter_web_snippets,
    build_person_research_queries,
    build_research_brief,
    dedupe_contacts_for_research,
)
from openrole.config import get_settings
from openrole.db.models import Company, Contact, Job
from openrole.db.session import init_db, session_scope
from openrole.schemas.research import PersonResearchBrief


def _seed_contact(monkeypatch):
    db_session._engine = None
    db_session._SessionLocal = None
    get_settings.cache_clear()
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    init_db()

    with session_scope() as session:
        co = Company(name="Acme Labs", domain="acme.com")
        session.add(co)
        session.flush()
        job = Job(
            company_id=co.id,
            title="ML Research Engineer",
            department="ai research",
            description="Build ML systems for trading.",
            locations=["New York, NY"],
        )
        session.add(job)
        session.flush()
        contact = Contact(
            company_id=co.id,
            full_name="Jane Doe",
            title="Senior Research Engineer",
            linkedin_url="https://www.linkedin.com/in/janedoe",
            metadata_json={
                "tier": "TEAM_ENGINEER",
                "apollo_person_id": "apollo-123",
                "source_job_id": job.id,
            },
            priority_rank=1,
        )
        session.add(contact)
        session.commit()
        return contact.id, job.id


def test_build_person_research_queries_includes_linkedin_slug_and_research():
    queries = build_person_research_queries(
        full_name="Jane Doe",
        company_name="Acme Labs",
        title="Senior Research Engineer",
        job_title="ML Research Engineer",
        linkedin_slug="janedoe",
    )
    kinds = {q["kind"] for q in queries}
    assert "linkedin_profile" in kinds
    assert "linkedin_posts" in kinds
    assert "research" in kinds
    assert "technical" in kinds
    assert any("site:linkedin.com/in/janedoe" in q["query"] for q in queries)


def test_dedupe_contacts_prefers_full_name_and_linkedin():
    c1 = Contact(
        id="1",
        company_id="co",
        full_name="Nikhil Saxena",
        linkedin_url="https://www.linkedin.com/in/nsax",
        priority_rank=1,
    )
    c2 = Contact(
        id="2",
        company_id="co",
        full_name="Nikhil Sa***a",
        metadata_json={"apollo_person_id": "apollo-1"},
        priority_rank=4,
    )
    out = dedupe_contacts_for_research([c2, c1])
    assert len(out) == 1
    assert out[0].full_name == "Nikhil Saxena"


def test_filter_web_snippets_drops_wrong_person_and_aggregators():
    kept = _filter_web_snippets(
        [
            {
                "title": "Wrong person",
                "url": "https://inextwebtechnologies.com/team/nikhil",
                "content": "iOS developer in India",
            },
            {
                "title": "Directory",
                "url": "https://www.linkedin.com/pub/dir/Nikhil/Saxena",
                "content": "Nikhil Saxena Anthropic",
            },
            {
                "title": "Real post",
                "url": "https://www.linkedin.com/posts/nsax_test",
                "content": "Nikhil Saxena at Anthropic Safeguards",
            },
        ],
        company_name="Anthropic",
        linkedin_slug="nsax",
        contact_name="Nikhil Saxena",
    )
    assert len(kept) == 1
    assert "nsax" in kept[0]["url"]


def test_clean_synthesis_output_strips_placeholders():
    cleaned = _clean_synthesis_output(
        {
            "suggested_hook": "My background in [your research area] aligns well.",
            "outreach_angles": ["Good angle", "[insert project here]"],
        }
    )
    assert "[" not in cleaned["suggested_hook"]
    assert cleaned["outreach_angles"] == ["Good angle"]


@patch("openrole.agents.person_research.extract_url")
@patch("openrole.agents.person_research._synthesize_brief")
@patch("openrole.agents.person_research.search_web")
@patch("openrole.agents.person_research.tavily_ready", return_value=True)
@patch("openrole.agents.person_research.apollo_client.is_configured", return_value=True)
@patch("openrole.agents.person_research.apollo_client.match_person")
def test_build_research_brief_tavily_first_then_synthesis(
    mock_match,
    mock_apollo_cfg,
    mock_tavily_ready,
    mock_search,
    mock_synth,
    mock_extract,
    monkeypatch,
):
    contact_id, job_id = _seed_contact(monkeypatch)
    mock_match.return_value = {
        "id": "apollo-123",
        "first_name": "Jane",
        "last_name": "Doe",
        "title": "Senior Research Engineer",
        "headline": "ML systems at Acme",
        "linkedin_url": "https://www.linkedin.com/in/janedoe",
        "employment_history": [
            {
                "title": "Senior Research Engineer",
                "organization": {"name": "Acme Labs"},
                "current": True,
            }
        ],
    }
    mock_search.return_value = [
        {
            "title": "Jane on ML infra",
            "url": "https://example.com/blog/jane",
            "content": "Jane Doe at Acme Labs wrote about distributed training pipelines.",
            "score": 0.9,
        }
    ]
    mock_extract.return_value = None
    mock_synth.return_value = {
        "summary": "Jane builds ML infra at Acme.",
        "recent_work": "Distributed training for research teams.",
        "public_signals": [
            {
                "type": "blog",
                "summary": "Blog post on distributed training",
                "url": "https://example.com/blog/jane",
            }
        ],
        "outreach_angles": ["Reference her blog on distributed training"],
        "talking_points": ["Senior Research Engineer at Acme Labs"],
        "suggested_hook": "Your blog on distributed training resonated.",
        "tone_notes": "Peer technical tone.",
        "confidence": 0.82,
        "gaps": [],
    }

    with session_scope() as session:
        contact = session.get(Contact, contact_id)
        job = session.get(Job, job_id)
        brief = build_research_brief(
            contact=contact,
            job=job,
            company_name="Acme Labs",
            company_domain="acme.com",
        )

    assert isinstance(brief, PersonResearchBrief)
    assert "tavily" in brief.layers_used
    assert "apollo" in brief.layers_used
    assert "llm" in brief.layers_used
    assert brief.summary.startswith("Jane builds")
    assert brief.public_signals[0].type == "blog"
    assert len(brief.sources) <= 5
    assert all("content" not in s for s in brief.sources)
    mock_synth.assert_called_once()
    evidence = mock_synth.call_args[0][0]
    assert evidence["apollo_facts"]["headline"] == "ML systems at Acme"
    assert evidence["web_snippets"]


@patch("openrole.agents.person_research._synthesize_brief", return_value=None)
@patch("openrole.agents.person_research.tavily_ready", return_value=False)
@patch("openrole.agents.person_research.apollo_client.is_configured", return_value=False)
def test_build_research_brief_fallback_when_llm_unavailable(
    mock_apollo_cfg,
    mock_tavily_ready,
    mock_synth,
    monkeypatch,
):
    contact_id, job_id = _seed_contact(monkeypatch)

    with session_scope() as session:
        contact = session.get(Contact, contact_id)
        job = session.get(Job, job_id)
        brief = build_research_brief(contact=contact, job=job, company_name="Acme Labs")

    assert brief.confidence == pytest.approx(0.35)
    assert brief.suggested_hook
    assert any("LLM" in g or "Tavily" in g for g in brief.gaps)


@patch("openrole.agents.person_research.apollo_client.match_person")
@patch("openrole.agents.person_research.apollo_client.find_person_by_name")
@patch("openrole.agents.person_research.apollo_client.is_configured", return_value=True)
@patch("openrole.agents.person_research.tavily_ready", return_value=False)
@patch("openrole.agents.person_research._synthesize_brief")
def test_apollo_backfill_when_no_person_id(
    mock_synth,
    mock_tavily,
    mock_apollo_cfg,
    mock_find,
    mock_match,
    monkeypatch,
):
    contact_id, job_id = _seed_contact(monkeypatch)
    with session_scope() as session:
        contact = session.get(Contact, contact_id)
        contact.metadata_json = {"tier": "TEAM_ENGINEER", "source_job_id": job_id}
        session.commit()

    mock_find.return_value = {"id": "found-99", "first_name": "Jane", "last_name": "Doe"}
    mock_match.return_value = {
        "id": "found-99",
        "first_name": "Jane",
        "last_name": "Doe",
        "title": "Senior Research Engineer",
        "headline": "ML at Acme",
    }
    mock_synth.return_value = {
        "summary": "Jane at Acme",
        "recent_work": "ML",
        "public_signals": [],
        "outreach_angles": ["Angle"],
        "talking_points": ["Point"],
        "suggested_hook": "Hi Jane",
        "tone_notes": "Peer",
        "confidence": 0.7,
        "gaps": [],
    }

    with session_scope() as session:
        contact = session.get(Contact, contact_id)
        job = session.get(Job, job_id)
        brief = build_research_brief(
            contact=contact,
            job=job,
            company_name="Acme Labs",
            company_domain="acme.com",
        )

    assert "apollo_backfill" in brief.layers_used
    mock_find.assert_called_once()
