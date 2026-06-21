"""Tests for Tavily people discovery query building and parsing."""

from openrole.agents.tavily_people_discovery import (
    TAVILY_QUERY_TEMPLATES,
    _parse_linkedin_profiles,
    build_tavily_query_specs,
    normalize_company_search_name,
)
from openrole.db.models import Job
from openrole.schemas.job_context import JobSearchContext
from openrole.scrapers.location_match import parse_job_locations


def test_normalize_company_search_name():
    assert normalize_company_search_name("Amazon.com Services LLC") == "Amazon"
    assert normalize_company_search_name("Anthropic") == "Anthropic"
    assert normalize_company_search_name("Meta Platforms, Inc.") == "Meta"


def test_build_tavily_query_specs_includes_passes():
    job = Job(
        title="Research Engineer, Safeguards Labs",
        department="Safeguards Labs",
        locations=["San Francisco, CA", "New York City, NY"],
    )
    ctx = JobSearchContext(
        department_name="Safeguards Labs",
        department_keywords=["safeguards"],
        office_locations=job.locations or [],
    )
    loc = parse_job_locations(ctx.office_locations)
    specs = build_tavily_query_specs(
        company="Anthropic",
        job=job,
        search_context=ctx,
        location_target=loc,
    )
    types = {s["query_type"] for s in specs}
    assert "company_wide" in types
    assert "department" in types
    assert "department_location" in types
    assert "role_title" in types
    dept_query = next(s for s in specs if s["query_type"] == "department")
    assert "Safeguards" in dept_query["query"]
    assert "site:linkedin.com/in" in dept_query["query"]


def test_parse_linkedin_profiles_from_tavily_rows():
    rows = [
        {"title": "summary", "content": "ignored", "url": ""},
        {
            "title": "Erin McAweeney - Safeguards @ Anthropic",
            "url": "https://www.linkedin.com/in/erin-mcaweeney",
            "content": "Erin McAweeney Safeguards @ Anthropic Washington, District of Columbia, United States",
            "score": 0.9,
        },
    ]
    profiles = _parse_linkedin_profiles(
        rows,
        query_type="department",
        query='"safeguards" "Anthropic" site:linkedin.com/in',
    )
    assert len(profiles) == 1
    assert profiles[0]["full_name"] == "Erin McAweeney"
    assert profiles[0]["linkedin_url"] == "https://www.linkedin.com/in/erin-mcaweeney"
    assert "Safeguards" in (profiles[0]["title"] or "")


def test_query_templates_documented():
    assert "company" in TAVILY_QUERY_TEMPLATES["company_wide"]
    assert "department_terms" in TAVILY_QUERY_TEMPLATES["department"]
