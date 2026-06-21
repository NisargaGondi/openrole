"""Tests for ATS board listing helpers."""

from unittest.mock import patch

from openrole.scrapers.ats_apis import list_greenhouse_jobs


@patch("openrole.scrapers.ats_apis._get_json")
def test_list_greenhouse_jobs(mock_get):
    mock_get.return_value = {
        "jobs": [
            {
                "id": 1,
                "title": "Engineer",
                "absolute_url": "https://boards.greenhouse.io/acme/jobs/1",
                "content": "<p>Build things</p>",
                "locations": [{"name": "Remote"}],
            }
        ]
    }
    jobs = list_greenhouse_jobs("acme")
    assert len(jobs) == 1
    assert jobs[0]["title"] == "Engineer"
    assert "Build things" in jobs[0]["content"]
