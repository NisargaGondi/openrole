"""Tests for LLM ingestion enrichment helpers."""

from openrole.agents.ingestion_prompts import build_ingestion_user_message, scraper_hints_from_parsed
from openrole.agents.job_ingestion import _coerce_locations, _normalize_visa_status, _raw_content_for_enrich
from openrole.agents.scout_filter import assess_opt_status
from openrole.schemas.job import ParsedJob


def test_scraper_hints_from_parsed():
    job = ParsedJob(
        title="ML Engineer",
        company_name="Meta",
        department="AI",
        locations=["Menlo Park, CA"],
    )
    hints = scraper_hints_from_parsed(job)
    assert hints["title"] == "ML Engineer"
    assert hints["locations"] == ["Menlo Park, CA"]


def test_scraper_hints_include_handshake_visa():
    job = ParsedJob(
        title="Intern",
        company_name="Co",
        raw_payload={"metadata": {"accepts_opt": True, "will_sponsor": False}},
    )
    hints = scraper_hints_from_parsed(job)
    assert hints["handshake_visa"]["accepts_opt"] is True


def test_normalize_visa_status():
    assert _normalize_visa_status("Eligible") == "eligible"
    assert _normalize_visa_status("unknown") == "unknown"
    assert _normalize_visa_status("maybe") is None


def test_assess_opt_status_uses_llm_enrich():
    job = ParsedJob(
        title="SWE",
        company_name="Co",
        description="No visa mention.",
        raw_payload={"llm_enrich": {"visa_status": "eligible", "accepts_opt": True}},
    )
    assert assess_opt_status(job.description or "", job) == "eligible"


def test_coerce_locations_dedupes():
    assert _coerce_locations(["Austin, TX", "Austin, TX", ""]) == ["Austin, TX"]


def test_raw_content_prefers_greenhouse_html():
    parsed = ParsedJob(
        title="Eng",
        company_name="Co",
        description="plain strip",
        raw_payload={"content": "<p>Full <strong>HTML</strong> JD</p>"},
    )
    assert "HTML" in _raw_content_for_enrich(parsed, None)


def test_build_user_message_includes_hints():
    msg = build_ingestion_user_message(
        source_url="https://example.com/job",
        source_platform="universal",
        scraper_hints={"title": "Eng"},
        raw_content="Bellevue, WA · Menlo Park, CA\nSoftware Engineer",
    )
    assert "scraper_hints" in msg
    assert "Bellevue" in msg
    assert "F-1" in msg
