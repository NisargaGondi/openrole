"""Tests for location matching and people discovery ranking."""

from unittest.mock import patch

import pytest

from openrole.agents.people_discovery import (
    PeopleDiscoveryError,
    _classify_tier,
    _is_hiring_manager_title,
    _merge_duplicate_contact,
    _normalize_linkedin,
    discover_people_for_job,
)
from openrole.db.models import Company, Contact, Job, JobStatus
from openrole.db.session import init_db, session_scope
from openrole.schemas.contact import ContactTier, DiscoveredContact
from openrole.scrapers.location_match import (
    email_actionable,
    parse_job_locations,
    score_person_location,
)


def _seed_job(*, domain: str = "acme.com", locations=None) -> str:
    import openrole.db.session as db_session
    from openrole.config import get_settings

    db_session._engine = None
    db_session._SessionLocal = None
    get_settings.cache_clear()
    init_db()

    with session_scope() as session:
        company = Company(name="Acme Corp", domain=domain)
        session.add(company)
        session.flush()
        job = Job(
            company_id=company.id,
            title="Machine Learning Engineer",
            department="AI Research",
            locations=locations or ["San Jose, CA"],
            status=JobStatus.DISCOVERED,
        )
        session.add(job)
        session.flush()
        return job.id


def test_parse_us_job_location():
    target = parse_job_locations(["San Jose, CA, United States"])
    assert target.us_only is True
    assert "United States" in target.apollo_person_locations


def test_india_location_heavily_penalized():
    target = parse_job_locations(["San Jose, CA"])
    penalty, reason = score_person_location(
        location="Bangalore, India",
        title="Engineering Manager",
        target=target,
    )
    assert penalty >= 150
    assert "India" in reason


def test_academic_email_not_actionable():
    ok, reason = email_actionable(email="akash@abes.ac.in", company_domain="cadence.com")
    assert ok is False
    assert "Non-company" in reason


def test_company_email_actionable():
    ok, _ = email_actionable(email="pat@cadence.com", company_domain="cadence.com")
    assert ok is True


def test_lead_engineer_not_classified_as_manager():
    assert _is_hiring_manager_title("lead research & software engineer") is False


def test_engineering_manager_is_hiring_manager():
    assert _is_hiring_manager_title("sr. engineering manager") is True


def test_india_recruiter_tier():
    tier, _reason = _classify_tier(
        title="Director Talent Acquisition (India)",
        person={},
        job_title="ml engineer",
        department="",
        dept_keywords=[],
        company_name="Cadence",
        cmu_domain="andrew.cmu.edu",
    )
    assert tier in (ContactTier.GENERAL_RECRUITER, ContactTier.OTHER)


def test_classify_hiring_manager():
    tier, _reason = _classify_tier(
        title="Engineering Manager, AI Research",
        person={},
        job_title="machine learning engineer",
        department="ai research",
        dept_keywords=["ai research"],
        company_name="Acme",
        cmu_domain="andrew.cmu.edu",
    )
    assert tier == ContactTier.HIRING_MANAGER


def test_classify_executive_head_of():
    tier, _reason = _classify_tier(
        title="Head of Safeguards Engineering",
        person={},
        job_title="research engineer",
        department="safeguards",
        dept_keywords=["safeguard"],
        company_name="Anthropic",
        cmu_domain="andrew.cmu.edu",
    )
    assert tier == ContactTier.EXECUTIVE


def test_strict_city_excludes_wrong_metro():
    from openrole.agents.contact_validation import build_location_target, validate_contacts
    from openrole.schemas.job_context import JobSearchContext

    ctx = JobSearchContext(office_locations=["San Jose, CA"])
    loc = build_location_target(ctx)
    assert loc.strict_cities is True
    c_good = DiscoveredContact(
        full_name="Pat",
        title="Security Manager",
        location="San Jose, CA",
        relevance_score=800,
        priority_reason="test",
    )
    c_bad = DiscoveredContact(
        full_name="Akash",
        title="Engineering Manager",
        location="Bangalore, India",
        relevance_score=800,
        priority_reason="test",
    )
    out = validate_contacts([c_good, c_bad], search_context=ctx, location_target=loc)
    assert out["validated_count"] == 1
    assert out["contacts"][0].full_name == "Pat"
    assert len(out["location_rejected"]) == 1
    assert out["location_rejected"][0].full_name == "Akash"


def test_location_backfill_adds_rejected_when_few_pass():
    from openrole.agents.contact_validation import (
        backfill_location_contacts,
        build_location_target,
        validate_contacts,
    )
    from openrole.schemas.job_context import JobSearchContext

    ctx = JobSearchContext(office_locations=["New York, NY"])
    loc = build_location_target(ctx)
    contacts = [
        DiscoveredContact(
            full_name="Local",
            title="ML Engineer",
            location="New York, NY",
            relevance_score=900,
        ),
        DiscoveredContact(
            full_name="Remote US",
            title="Research Engineer",
            location="Seattle, WA",
            relevance_score=850,
        ),
        DiscoveredContact(
            full_name="India",
            title="Engineer",
            location="Bangalore, India",
            relevance_score=800,
        ),
    ]
    out = validate_contacts(contacts, search_context=ctx, location_target=loc)
    assert out["validated_count"] == 1
    filled = backfill_location_contacts(
        out["contacts"],
        out["location_rejected"],
        min_target=5,
        max_total=20,
    )
    assert len(filled) == 3
    names = [c.full_name for c in filled]
    assert "Local" in names
    assert "Remote US" in names
    assert filled[1].metadata_json.get("location_backfill") is True


def test_rank_contacts_empty_department_keywords(monkeypatch):
    """Jobs without department context must not crash ranking."""
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    job_id = _seed_job(locations=None)
    with session_scope() as session:
        from openrole.agents.job_context import build_job_search_context
        from openrole.agents.people_discovery import _rank_contacts
        from openrole.scrapers.location_match import parse_job_locations

        job = session.get(Job, job_id)
        assert job is not None
        job.description = None
        job.department = None
        ctx = build_job_search_context(job)
        loc = parse_job_locations(job.locations)
        ranked = _rank_contacts(
            [
                {
                    "id": "p1",
                    "first_name": "Pat",
                    "last_name": "Lee",
                    "title": "Engineering Manager",
                    "city": "San Jose",
                    "state": "CA",
                    "country": "United States",
                    "has_email": True,
                }
            ],
            job=job,
            company_name="Acme Corp",
            company_domain="acme.com",
            location_target=loc,
            search_context=ctx,
        )
        assert len(ranked) == 1
        assert ranked[0].full_name == "Pat Lee"


@patch("openrole.agents.people_discovery.discover_people_via_tavily", return_value=([], []))
@patch("openrole.agents.people_discovery.careershift_client.is_ready", return_value=False)
@patch("openrole.agents.people_discovery.build_job_search_context")
@patch("openrole.agents.people_discovery.apollo_client.match_person")
@patch("openrole.agents.people_discovery.apollo_client.search_people")
@patch("openrole.agents.people_discovery.apollo_client.enrich_organization")
def test_discover_prefers_us_manager(
    mock_enrich, mock_search, mock_match, mock_ctx, _mock_cs, _mock_tavily, monkeypatch
):
    from openrole.schemas.job_context import JobSearchContext

    mock_ctx.return_value = JobSearchContext(
        office_locations=["San Jose, CA"],
        department_name="AI Research",
        department_keywords=["ai research"],
    )
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("APOLLO_API_KEY", "test-key")
    monkeypatch.setenv("APOLLO_ENABLED", "true")
    from openrole.config import get_settings

    get_settings.cache_clear()

    job_id = _seed_job()
    mock_enrich.return_value = {"id": "org-1"}
    mock_match.return_value = {
        "id": "p-us",
        "first_name": "Pat",
        "last_name": "Manager",
        "title": "Engineering Manager, AI Research",
        "email": "pat@acme.com",
        "city": "San Jose",
        "state": "California",
        "country": "United States",
    }

    def _search_side_effect(*, domain, person_titles=None, q_keywords=None, **kwargs):
        titles_blob = " ".join(person_titles or []).lower()
        if "manager" in titles_blob or (q_keywords and "ai" in str(q_keywords).lower()):
            return [
                {
                    "id": "p-us",
                    "first_name": "Pat",
                    "last_name": "Manager",
                    "title": "Engineering Manager, AI Research",
                    "city": "San Jose",
                    "state": "California",
                    "country": "United States",
                    "has_email": True,
                },
                {
                    "id": "p-in",
                    "first_name": "Akash",
                    "last_name": "Gupta",
                    "title": "Sr. Engineering Manager",
                    "city": "Bangalore",
                    "country": "India",
                    "email": "akash@abes.ac.in",
                    "has_email": True,
                },
            ]
        return []

    mock_search.side_effect = _search_side_effect

    result = discover_people_for_job(job_id, enrich_top_n=5)
    assert result["contact_count"] >= 1
    with session_scope() as session:
        top = session.scalar(
            __import__("sqlalchemy").select(Contact).order_by(Contact.priority_rank).limit(1)
        )
        assert top is not None
        assert "Manager" in (top.title or "")
        assert top.email == "pat@acme.com"


def test_discover_without_domain_and_no_tavily_fails(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("APOLLO_API_KEY", "test-key")
    job_id = _seed_job(domain="")
    with patch("openrole.agents.people_discovery.resolve_company_domain", return_value=None):
        with patch("openrole.agents.people_discovery.discover_people_via_tavily", return_value=([], [])):
            with pytest.raises(PeopleDiscoveryError, match="No people sources returned"):
                discover_people_for_job(job_id)


def test_compute_discovery_source():
    from openrole.schemas.contact import (
        DISCOVERY_SOURCE_APOLLO,
        DISCOVERY_SOURCE_BOTH,
        DISCOVERY_SOURCE_CAREERSHIFT,
        DISCOVERY_SOURCE_TAVILY,
        compute_discovery_source,
        discovery_source_label,
    )

    assert compute_discovery_source({"apollo_search": True}) == DISCOVERY_SOURCE_APOLLO
    assert compute_discovery_source({"careershift_search": True}) == DISCOVERY_SOURCE_CAREERSHIFT
    assert compute_discovery_source({"tavily_search": True}) == DISCOVERY_SOURCE_TAVILY
    assert (
        compute_discovery_source({"apollo_search": True, "careershift_search": True})
        == DISCOVERY_SOURCE_BOTH
    )
    assert discovery_source_label({"tavily_search": True}) == "Tavily"
    assert discovery_source_label({"tavily_search": True, "apollo_search": True}) == (
        "Tavily · Apollo"
    )
    assert discovery_source_label({"careershift_search": True}) == "CareerShift"


def test_rank_contacts_merges_same_email_across_sources():
    from openrole.agents.contact_validation import build_location_target
    from openrole.agents.people_discovery import _rank_contacts
    from openrole.schemas.contact import DISCOVERY_SOURCE_BOTH
    from openrole.schemas.job_context import JobSearchContext

    job = Job(title="Software Engineer", department="Engineering", locations=["San Francisco, CA"])
    ctx = JobSearchContext(
        department_name="Engineering",
        office_locations=["San Francisco"],
        hiring_manager_titles=["engineering manager"],
    )
    loc = build_location_target(ctx)
    raw = [
        {
            "id": "apollo-1",
            "first_name": "Pat",
            "last_name": "Lee",
            "title": "Engineering Manager",
            "email": "pat@acme.com",
            "city": "San Francisco",
            "state": "California",
            "country": "United States",
        },
        {
            "_openrole_careershift": True,
            "id": "cs-1",
            "first_name": "Pat",
            "last_name": "Lee",
            "title": "Engineering Manager",
            "email": "pat@acme.com",
            "location": "San Francisco, CA",
            "careershift_id": "cs-1",
        },
    ]
    ranked = _rank_contacts(
        raw,
        job=job,
        company_name="Acme",
        company_domain="acme.com",
        location_target=loc,
        search_context=ctx,
    )
    assert len(ranked) == 1
    assert ranked[0].metadata_json["discovery_source"] == DISCOVERY_SOURCE_BOTH


def test_linkedin_dedupe_merge():
    from openrole.schemas.contact import DISCOVERY_SOURCE_BOTH, DiscoveredContact

    a = DiscoveredContact(
        full_name="Pat",
        linkedin_url="https://linkedin.com/in/pat-lee",
        metadata_json={"apollo_search": True, "careershift_search": False},
        relevance_score=500,
    )
    _merge_duplicate_contact(
        a,
        raw={"_openrole_careershift": True},
        fields={"careershift_id": "cs-1", "linkedin_url": "https://linkedin.com/in/pat-lee"},
        is_careershift=True,
        relevance=800,
    )
    assert a.metadata_json["discovery_source"] == DISCOVERY_SOURCE_BOTH
    assert a.relevance_score == 800


def test_normalize_linkedin():
    assert _normalize_linkedin("https://www.linkedin.com/in/pat-lee/") == "pat-lee"


def test_llm_scores_all_contacts_in_one_call():
    from unittest.mock import MagicMock

    from openrole.agents.contact_relevance import score_contacts_with_llm
    from openrole.db.models import Job
    from openrole.schemas.job_context import JobSearchContext

    contacts = [
        DiscoveredContact(full_name=f"Person {i}", title="Engineer", relevance_score=600)
        for i in range(30)
    ]
    job = Job(id="j1", title="ML Engineer", company_id="c1")
    ctx = JobSearchContext(department_name="ML")
    scores_json = {
        "scores": [
            {"full_name": c.full_name, "relevance": 70, "in_target_department": True, "contact_type": "team_engineer"}
            for c in contacts
        ]
    }
    fake_response = MagicMock()
    fake_response.content = __import__("json").dumps(scores_json)

    with patch("openrole.agents.contact_relevance.get_settings") as gs:
        gs.return_value.llm_configured = True
        with patch("openrole.agents.contact_relevance.get_chat_model") as gcm:
            gcm.return_value.invoke.return_value = fake_response
            result, _ = score_contacts_with_llm(
                contacts,
                job=job,
                search_context=ctx,
                company_name="Acme",
            )

    assert len(result) == 30
    gcm.return_value.invoke.assert_called_once()
    human = gcm.return_value.invoke.call_args[0][0][1].content
    assert "30 total" in human
    assert "Person 29" in human
