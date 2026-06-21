"""Tests for SPA JSON-LD hint extraction."""

from openrole.scrapers.spa_hints import (
    extract_job_posting_json_ld,
    extract_spa_hints,
    format_structured_metadata_block,
)


_META_SNIPPET = """
{"@context":"http://schema.org","@type":"JobPosting","title":"Software Engineer, Systems ML",
"hiringOrganization":{"@type":"Organization","name":"Meta"},
"jobLocation":[{"@type":"Place","name":"Bellevue, WA"},{"@type":"Place","name":"Menlo Park, CA"},
{"@type":"Place","name":"New York, NY"}],
"description":"Meta is seeking a Research Engineer specializing in Systems Machine Learning.",
"responsibilities":"Design ML systems","qualifications":"BS in CS","employmentType":"Full-time"}
"""


def test_extract_meta_job_posting():
    hints = extract_spa_hints("https://www.metacareers.com/profile/job_details/123/", _META_SNIPPET)
    assert hints is not None
    assert hints["title"] == "Software Engineer, Systems ML"
    assert hints["company_name"] == "Meta"
    assert "Bellevue, WA" in hints["locations"]
    assert hints["department"] == "Artificial Intelligence"


def test_format_structured_metadata_block():
    block = format_structured_metadata_block(
        {
            "title": "SWE",
            "company_name": "Meta",
            "locations": ["Bellevue, WA", "New York, NY"],
            "department": "Artificial Intelligence",
        }
    )
    assert "STRUCTURED PAGE METADATA" in block
    assert "Bellevue, WA" in block
    assert "Artificial Intelligence" in block


def test_extract_job_posting_json_ld_from_script_tag():
    html = f'<html><script type="application/ld+json">{_META_SNIPPET}</script></html>'
    posting = extract_job_posting_json_ld(html)
    assert posting is not None
    assert posting["title"] == "Software Engineer, Systems ML"
