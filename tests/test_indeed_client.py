"""Tests for direct Indeed viewjob fetch."""

from unittest.mock import patch

import pytest

from openrole.scrapers.indeed_client import (
    IndeedFetchError,
    fetch_indeed_by_job_key,
    indeed_job_key_from_url,
)


def test_indeed_job_key_from_url():
    url = "https://www.indeed.com/viewjob?jk=20d6cd86199bba1e&from=share"
    assert indeed_job_key_from_url(url) == "20d6cd86199bba1e"


@patch("openrole.scrapers.indeed_client._fetch_html")
def test_fetch_indeed_by_job_key_parses_json_ld(mock_html):
    mock_html.return_value = """
    <html><head></head><body>
    <script type="application/ld+json">
    {
      "@type": "JobPosting",
      "title": "Machine Learning Engineer II",
      "description": "<p>Build ML systems</p>",
      "hiringOrganization": {"name": "Amazon.com Services LLC"},
      "jobLocation": {
        "address": {"addressLocality": "New York", "addressRegion": "NY"}
      }
    }
    </script>
 20d6cd86199bba1e
    </body></html>
    """
    parsed = fetch_indeed_by_job_key(
        "20d6cd86199bba1e",
        source_url="https://www.indeed.com/viewjob?jk=20d6cd86199bba1e",
    )
    assert parsed.title == "Machine Learning Engineer II"
    assert parsed.company_name == "Amazon.com Services LLC"
    assert parsed.locations == ["New York, NY"]
    assert parsed.external_id == "20d6cd86199bba1e"


@patch("openrole.scrapers.indeed_client._fetch_html")
def test_fetch_indeed_rejects_missing_job_key(mock_html):
    mock_html.return_value = "<html><body>blocked</body></html>"
    with pytest.raises(IndeedFetchError, match="did not contain job key"):
        fetch_indeed_by_job_key("20d6cd86199bba1e")
