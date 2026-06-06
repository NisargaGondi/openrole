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


@patch("openrole.agents.people_discovery.build_job_search_context")
@patch("openrole.agents.people_discovery.apollo_client.match_person")
@patch("openrole.agents.people_discovery.apollo_client.search_people")
@patch("openrole.agents.people_discovery.apollo_client.enrich_organization")
def test_discover_prefers_us_manager(
    mock_enrich, mock_search, mock_match, mock_ctx, monkeypatch
):
    from openrole.schemas.job_context import JobSearchContext

    mock_ctx.return_value = JobSearchContext(
        office_locations=["San Jose, CA"],
        department_name="AI Research",
        department_keywords=["ai research"],
    )
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("APOLLO_API_KEY", "test-key")

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

    def _search_side_effect(*, domain, person_titles=None, **kwargs):
        if person_titles and "manager" in person_titles[0]:
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


def test_discover_requires_domain(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("APOLLO_API_KEY", "test-key")
    job_id = _seed_job(domain="")
    with patch("openrole.agents.people_discovery.resolve_company_domain", return_value=None):
        with pytest.raises(PeopleDiscoveryError, match="No company domain"):
            discover_people_for_job(job_id)


def test_compute_discovery_source():
    from openrole.schemas.contact import (
        DISCOVERY_SOURCE_APOLLO,
        DISCOVERY_SOURCE_BOTH,
        DISCOVERY_SOURCE_CAREERSHIFT,
        compute_discovery_source,
        discovery_source_label,
    )

    assert compute_discovery_source({"apollo_search": True}) == DISCOVERY_SOURCE_APOLLO
    assert compute_discovery_source({"careershift_search": True}) == DISCOVERY_SOURCE_CAREERSHIFT
    assert (
        compute_discovery_source({"apollo_search": True, "careershift_search": True})
        == DISCOVERY_SOURCE_BOTH
    )
    assert discovery_source_label({"careershift_search": True}) == "CareerShift"
    assert discovery_source_label({"apollo_search": True, "careershift_search": True}) == (
        "Apollo + CareerShift"
    )


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
