"""Tests for CareerShift auth and JSON parsing."""

from openrole.scrapers.careershift_auth import (
    CONTACTS_SEARCH_URL,
    _is_app_url,
    _is_login_url,
)
from openrole.scrapers.careershift_client import (
    _extract_contacts_from_json,
    _looks_like_contact,
    _looks_like_person_name,
    _normalize_contact_row,
    to_ranking_person,
)


def test_login_url_detected():
    assert _is_login_url("https://www.careershift.com/Account/Login")
    assert _is_login_url("https://app.careershift.com/login")
    assert _is_login_url("https://www.careershift.com/user/signup?group=CMU")


def test_app_url_new_host():
    assert _is_app_url("https://app.careershift.com/contacts/search")
    assert _is_app_url(CONTACTS_SEARCH_URL)


def test_app_url_legacy_host():
    assert _is_app_url("https://www.careershift.com/App/Contacts/Search")


def test_contacts_search_not_login():
    assert not _is_login_url("https://app.careershift.com/contacts/search")


def test_looks_like_contact():
    row = {"firstName": "Ada", "lastName": "Lovelace", "title": "Engineer", "email": "ada@co.com"}
    assert _looks_like_contact(row)


def test_extract_contacts_from_nested_json():
    payload = {
        "results": [
            {
                "contactId": "42",
                "firstName": "Ravi",
                "lastName": "Kumar",
                "title": "Engineering Manager",
                "email": "rkumar@cadence.com",
                "city": "San Jose",
                "state": "CA",
                "companyName": "Cadence",
            }
        ]
    }
    rows = _extract_contacts_from_json(payload)
    assert len(rows) == 1
    assert rows[0]["full_name"] == "Ravi Kumar"
    assert rows[0]["email"] == "rkumar@cadence.com"


def test_person_name_heuristic():
    assert _looks_like_person_name("Ismail Hussain")
    assert not _looks_like_person_name("Recommended contacts in Pennsylvania")
    assert not _looks_like_person_name("Search LinkedIn")


def test_normalize_api_contact():
    from openrole.scrapers.careershift_client import _normalize_api_contact

    row = _normalize_api_contact(
        {
            "externalId": "3246021627",
            "name": "Neil Robinson",
            "jobTitle": "Intel Tensilica IP Sales Executive",
            "companyName": "Cadence Design Systems",
            "hasEmail": True,
        }
    )
    assert row["full_name"] == "Neil Robinson"
    assert row["company"] == "Cadence Design Systems"
    assert row["has_email"] is True


def test_parse_result_card_text():
    from openrole.scrapers.careershift_client import _parse_result_card_text

    parsed = _parse_result_card_text(
        "Helen Bird\nCadence Design Systems | Director, Human Resources"
    )
    assert parsed["full_name"] == "Helen Bird"
    assert parsed["company"] == "Cadence Design Systems"
    assert "Director" in (parsed["title"] or "")


def test_to_ranking_person_marks_source():
    normalized = _normalize_contact_row(
        {
            "contactId": "99",
            "fullName": "Mark A",
            "title": "Technical Recruiter",
            "email": "mapton@cadence.com",
            "location": "San Jose, CA",
        }
    )
    person = to_ranking_person(normalized)
    assert person["id"] == "cs:99"
    assert person["_openrole_careershift"] is True
    assert person["has_email"] is True
