"""Tests for CareerShift contact validation."""

from openrole.scrapers.careershift_validate import validate_careershift_contact


def test_validate_accepts_good_contact():
    ok, reason, fields = validate_careershift_contact(
        {
            "full_name": "Pat Lee",
            "title": "Engineering Manager",
            "email": "pat@acme.com",
            "company": "Acme Corp",
            "location": "San Francisco, CA",
        },
        company_name="Acme Corp",
        company_domain="acme.com",
    )
    assert ok
    assert reason == "ok"
    assert fields["email"] == "pat@acme.com"


def test_validate_rejects_company_mismatch():
    ok, reason, _ = validate_careershift_contact(
        {"full_name": "Pat Lee", "title": "Mgr", "company": "Other Inc"},
        company_name="Acme Corp",
    )
    assert not ok
    assert "mismatch" in reason
