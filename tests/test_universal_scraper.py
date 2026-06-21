"""Tests for universal scraper and Indeed matching."""

from unittest.mock import patch

import pytest

from openrole.schemas.job import ParsedJob
from openrole.scrapers.universal import UniversalScrapeError, _html_to_text, fetch_page_text
from openrole.tools import jobspy_client


def test_indeed_no_silent_first_row_fallback():
    with patch("openrole.scrapers.indeed_client.fetch_indeed_by_job_key") as mock_direct, patch(
        "jobspy.scrape_jobs"
    ) as mock_scrape, patch(
        "openrole.db.repository.job_hints_for_url", return_value=(None, None)
    ):
        from openrole.scrapers.indeed_client import IndeedFetchError

        mock_direct.side_effect = IndeedFetchError("blocked")
        import pandas as pd

        mock_scrape.return_value = pd.DataFrame(
            [{"title": "Wrong job", "company": "Other Co", "job_url": "https://indeed.com/viewjob?jk=other"}]
        )
        with pytest.raises(ValueError, match="Could not match Indeed job"):
            jobspy_client.fetch_indeed_by_search(
                indeed_job_id="ead1c5b54e60df12",
                source_url="https://www.indeed.com/viewjob?jk=ead1c5b54e60df12",
            )


def test_html_to_text_strips_tags():
    html = "<html><body><h1>ML Engineer</h1><p>Build models at <b>Acme</b>.</p></body></html>"
    text = _html_to_text(html)
    assert "ML Engineer" in text
    assert "Acme" in text
    assert "<" not in text


@patch("openrole.scrapers.universal.extract_url")
def test_fetch_page_text_prefers_tavily(mock_extract):
    mock_extract.return_value = {"raw_content": "x" * 250, "url": "https://example.com/job"}
    text, source, hints = fetch_page_text("https://example.com/job")
    assert source.startswith("tavily")
    assert len(text) >= 200
    assert isinstance(hints, dict)


@patch("openrole.scrapers.universal.tavily_configured", return_value=False)
@patch("openrole.scrapers.universal._fetch_html")
def test_fetch_page_text_httpx_fallback(mock_html, _mock_tavily):
    mock_html.return_value = "<html><body>" + ("job description " * 30) + "</body></html>"
    text, source, hints = fetch_page_text("https://example.com/job")
    assert source == "httpx"
    assert len(text) >= 200
    assert isinstance(hints, dict)


@patch("openrole.tools.web_search.search_web")
@patch("openrole.scrapers.universal._fetch_html", side_effect=UniversalScrapeError("403"))
@patch("openrole.scrapers.universal.extract_url", return_value=None)
@patch("openrole.scrapers.universal.tavily_configured", return_value=True)
def test_fetch_page_text_tavily_search_fallback(_mock_tavily, _mock_extract, _mock_html, mock_search):
    mock_search.return_value = [{"title": "Role", "content": "x" * 250}]
    text, source, hints = fetch_page_text("https://blocked.example/job")
    assert source in ("tavily_search", "tavily_search_enriched")
    assert len(text) >= 200
    assert isinstance(hints, dict)


@patch("openrole.agents.job_ingestion.parse_job_page_text")
@patch("openrole.scrapers.universal.fetch_page_text")
def test_fetch_from_url(mock_text, mock_parse):
    from openrole.scrapers.universal import fetch_from_url

    mock_text.return_value = (
        "Senior Engineer\nAcme Corp\n",
        "tavily+json_ld",
        {"title": "Senior Engineer", "locations": ["NYC"]},
    )
    mock_parse.return_value = ParsedJob(
        title="Senior Engineer",
        company_name="Acme Corp",
        source_url="https://careers.example.com/jobs/1",
        source_platform="universal",
    )
    parsed = fetch_from_url("https://careers.example.com/jobs/1")
    assert parsed.title == "Senior Engineer"
    assert parsed.raw_payload["universal_fetch"]["source"] == "tavily+json_ld"
