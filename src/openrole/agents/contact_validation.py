"""Validate ranked contacts against job location + department context."""

from __future__ import annotations

from typing import Any

from openrole.schemas.contact import ContactTier, DiscoveredContact
from openrole.schemas.job_context import JobSearchContext
from openrole.scrapers.location_match import (
    JobLocationTarget,
    parse_job_locations,
    person_matches_department,
    score_person_location,
)

_MIN_RELEVANCE = 50
_MAX_CITY_PENALTY = 10


def validate_contacts(
    contacts: list[DiscoveredContact],
    *,
    search_context: JobSearchContext,
    location_target: JobLocationTarget,
    min_valid: int = 1,
) -> dict[str, Any]:
    strict_cities = location_target.strict_cities
    dept_keywords = search_context.apollo_department_queries()

    validated: list[DiscoveredContact] = []
    rejected_reasons: list[str] = []

    for contact in contacts:
        ok, reason = _contact_passes(
            contact,
            location_target=location_target,
            strict_cities=strict_cities,
            dept_keywords=dept_keywords,
        )
        if ok:
            contact.metadata_json["validation"] = "passed"
            validated.append(contact)
        else:
            contact.metadata_json["validation"] = f"rejected: {reason}"
            rejected_reasons.append(f"{contact.full_name}: {reason}")

    return {
        "ok": len(validated) >= min_valid,
        "contacts": validated,
        "validated_count": len(validated),
        "rejected_count": len(contacts) - len(validated),
        "rejected_sample": rejected_reasons[:5],
        "strict_cities": strict_cities,
        "department_keywords": dept_keywords,
        "retry_suggestion": "relax_city_filter" if not validated and strict_cities else None,
    }


def _contact_passes(
    contact: DiscoveredContact,
    *,
    location_target: JobLocationTarget,
    strict_cities: bool,
    dept_keywords: list[str],
) -> tuple[bool, str]:
    if contact.relevance_score < _MIN_RELEVANCE:
        return False, "low relevance score"

    loc_penalty, loc_reason = score_person_location(
        location=contact.location,
        title=contact.title,
        target=location_target,
    )
    if strict_cities and loc_penalty > _MAX_CITY_PENALTY:
        return False, loc_reason

    if dept_keywords:
        recruiters = contact.tier in (
            ContactTier.ROLE_RECRUITER,
            ContactTier.GENERAL_RECRUITER,
            ContactTier.CMU_ALUMNI,
        )
        if not recruiters and not person_matches_department(contact.title, dept_keywords):
            if contact.tier == ContactTier.HIRING_MANAGER and contact.relevance_score >= 750:
                pass
            elif contact.relevance_score < 720:
                return False, f"not in department ({', '.join(dept_keywords[:3])})"

    return True, "ok"


def build_location_target(search_context: JobSearchContext) -> JobLocationTarget:
    target = parse_job_locations(search_context.office_locations)
    if target.city_tokens:
        city_apollo = [
            loc for loc in target.apollo_person_locations if loc != "United States"
        ]
        if city_apollo:
            return JobLocationTarget(
                raw_locations=target.raw_locations,
                us_only=target.us_only,
                apollo_person_locations=tuple(city_apollo),
                city_tokens=target.city_tokens,
                state_tokens=target.state_tokens,
                strict_cities=True,
            )
    return target
