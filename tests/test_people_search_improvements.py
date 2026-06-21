"""Tests for email placeholder detection and department query expansion."""

from openrole.schemas.job_context import JobSearchContext
from openrole.scrapers.email_utils import clean_email, is_placeholder_email
from openrole.scrapers.location_match import person_matches_department


def test_placeholder_emails_rejected():
    assert is_placeholder_email("email@example.com")
    assert is_placeholder_email("example@example.com")
    assert clean_email("example@example.com") is None
    assert clean_email("pat@anthropic.com") == "pat@anthropic.com"


def test_expanded_department_queries_safeguards():
    ctx = JobSearchContext(
        department_name="Safeguards Labs",
        department_keywords=["safeguards"],
    )
    expanded = ctx.expanded_department_queries()
    assert any("safeguard" in q.lower() for q in expanded)
    assert any("ai safety" in q.lower() for q in expanded)


def test_person_matches_department_safeguards_variant():
    assert person_matches_department("Safeguards @ Anthropic", ["safeguard"])
    assert not person_matches_department("Head of Procurement", ["safeguards"])
