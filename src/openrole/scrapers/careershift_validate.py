"""Validate CareerShift contact fields before ranking/persist."""

from __future__ import annotations

import re
from typing import Any

_EMAIL_RE = re.compile(r"^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}$", re.I)
_PHONE_RE = re.compile(r"^\+?[\d\s().-]{7,}$")


def validate_careershift_contact(
    contact: dict[str, Any],
    *,
    company_name: str,
    company_domain: str | None = None,
) -> tuple[bool, str, dict[str, Any]]:
    """Return (ok, reason, validated_fields)."""
    name = (contact.get("full_name") or contact.get("name") or "").strip()
    if not name or name.lower() == "unknown":
        return False, "missing name", {}

    parts = name.split()
    if len(parts) < 2:
        return False, "name too short", {}

    title = (contact.get("title") or "").strip()
    email = _clean_email(contact.get("email"))
    location = (contact.get("location") or "").strip()
    phone = contact.get("phone") or contact.get("mobile")

    company = (contact.get("company") or "").strip()
    if company and company_name:
        if not _company_matches(company, company_name):
            return False, f"company mismatch ({company})", {}

    flags: list[str] = []
    if email:
        if not _EMAIL_RE.match(email):
            return False, f"invalid email format ({email})", {}
        if company_domain and not _email_at_domain(email, company_domain):
            flags.append("email_not_at_company_domain")
        else:
            flags.append("email_validated")
    else:
        flags.append("email_missing")

    if location:
        flags.append("location_present")
    if phone and _PHONE_RE.match(str(phone).strip()):
        flags.append("phone_present")

    validated = {
        "full_name": name,
        "title": title or None,
        "email": email,
        "location": location or None,
        "phone": str(phone).strip() if phone else None,
        "careershift_validation": {
            "passed": True,
            "flags": flags,
            "company_match": bool(company),
        },
    }
    return True, "ok", validated


def merge_validated_fields(contact: dict[str, Any], validated: dict[str, Any]) -> dict[str, Any]:
    merged = {**contact}
    for key, value in validated.items():
        if key == "careershift_validation":
            merged[key] = value
        elif value is not None:
            merged[key] = value
    return merged


def _clean_email(raw: Any) -> str | None:
    if not raw:
        return None
    email = str(raw).strip().lower()
    if email in ("email@example.com", "n/a", "none", "-"):
        return None
    return email if _EMAIL_RE.match(email) else None


def _company_matches(found: str, expected: str) -> bool:
    a = re.sub(r"[^a-z0-9]+", " ", found.lower()).split()
    b = re.sub(r"[^a-z0-9]+", " ", expected.lower()).split()
    if not a or not b:
        return True
    return a[0] == b[0] or b[0] in found.lower() or a[0] in expected.lower()


def _email_at_domain(email: str, company_domain: str) -> bool:
    domain = email.split("@")[-1].lower()
    cd = company_domain.lower().lstrip("@")
    return domain == cd or domain.endswith(f".{cd}")
