"""Tests for Tavily job discovery (URL parsing and query building)."""

from unittest.mock import patch

from openrole.agents.tavily_job_discovery import (
    TAVILY_JOB_QUERY_TEMPLATES,
    build_tavily_job_query_specs,
    enrich_job_url,
    extract_job_urls,
)
from openrole.db.models import Company


def test_extract_job_urls_greenhouse_lever_workday():
    text = """
    Apply at https://boards.greenhouse.io/anthropic/jobs/123456
    or https://jobs.lever.co/stripe/abc-def-123
    or https://amazon.wd5.myworkdayjobs.com/en-US/careers/job/Seattle/ML-Engineer_123
    """
    urls = extract_job_urls(text)
    assert any("greenhouse.io/anthropic/jobs/123456" in u for u in urls)
    assert any("jobs.lever.co/stripe" in u for u in urls)
    assert any("myworkdayjobs.com" in u and "/job/" in u for u in urls)


def test_build_tavily_job_query_specs_includes_ats_and_company():
    companies = [
        Company(
            name="Anthropic",
            domain="anthropic.com",
            metadata_json={"tier": "ambitious", "greenhouse_token": "anthropic"},
        ),
        Company(
            name="Stripe",
            domain="stripe.com",
            metadata_json={"tier": "moderate", "greenhouse_token": "stripe"},
        ),
    ]
    specs = build_tavily_job_query_specs(
        search_terms=["machine learning engineer"],
        companies=companies,
        max_companies=5,
    )
    types = {s["query_type"] for s in specs}
    assert "ats_boards" in types
    assert "company_ats" in types
    assert "company_domain" in types
    assert any("anthropic.com" in s["query"] for s in specs)


def test_enrich_job_url_snippet_fallback():
    parsed = enrich_job_url(
        "https://careers.example.com/jobs/ml-engineer",
        company_hint="Example Co",
        title_hint="ML Engineer",
        snippet="Build ML pipelines with PyTorch.",
        platform_hint="careers_page",
    )
    assert parsed is not None
    assert parsed.title == "ML Engineer"
    assert parsed.company_name == "Example Co"
    assert parsed.raw_payload.get("_openrole_tavily") is True


@patch("openrole.scrapers.ats_apis.fetch_from_ats")
def test_enrich_job_url_greenhouse_api(mock_fetch):
    from openrole.schemas.job import ParsedJob

    mock_fetch.return_value = ParsedJob(
        title="Research Engineer",
        company_name="Anthropic",
        description="Full JD from API",
        source_url="https://boards.greenhouse.io/anthropic/jobs/1",
        source_platform="greenhouse",
    )
    parsed = enrich_job_url(
        "https://boards.greenhouse.io/anthropic/jobs/1",
        snippet="snippet",
    )
    assert parsed is not None
    assert parsed.title == "Research Engineer"
    mock_fetch.assert_called_once()


def test_query_templates_documented():
    assert "term" in TAVILY_JOB_QUERY_TEMPLATES["ats_boards"]
    assert "company" in TAVILY_JOB_QUERY_TEMPLATES["company_ats"]
