"""Validate ranked contacts against job location + department context."""

from __future__ import annotations

import re
from typing import Any

from openrole.agents.outreach_prompts import is_leadership_tier
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
_MAX_CITY_PENALTY_UNKNOWN = 45
_MAX_UNRELATED_HIRING_MANAGERS = 8
_MIN_SCORE_WITHOUT_DEPT = 520
_MIN_CONTACTS_TARGET = 5

_ENGINEERING_JOB_RE = re.compile(
    r"\b(engineer|developer|scientist|researcher|swe\b|sde\b|ml\b|machine learning)\b",
    re.I,
)
_ENGINEERING_TITLE_SIGNAL_RE = re.compile(
    r"\b(engineer|engineering|developer|scientist|researcher|ml\b|machine learning|tech)\b",
    re.I,
)
_NON_ENGINEERING_FUNCTION_RE = re.compile(
    r"\b("
    r"sales|business development|\bbd\b|account executive|global agency|"
    r"agency development|retail ad|partnerships|marketing|commercial|"
    r"revenue|brand strategist|account manager|client partner"
    r")\b",
    re.I,
)
_SENIOR_LEADER_RE = re.compile(
    r"\b(vp|vice president|svp|evp)\b",
    re.I,
)


def is_engineering_role_job(job_title: str | None) -> bool:
    return bool(job_title and _ENGINEERING_JOB_RE.search(job_title))


def wrong_function_for_engineering_job(
    contact_title: str | None,
    *,
    job_title: str | None,
) -> str | None:
    """Return rejection reason when a contact is a poor fit for an engineering opening."""
    if not contact_title or not is_engineering_role_job(job_title):
        return None
    title_l = contact_title.lower()
    if _NON_ENGINEERING_FUNCTION_RE.search(title_l):
        return "non-engineering function for engineering role"
    if _SENIOR_LEADER_RE.search(title_l) and not _ENGINEERING_TITLE_SIGNAL_RE.search(title_l):
        return "senior leader outside engineering org"
    return None


def _is_location_rejection(reason: str) -> bool:
    """True when contact failed validation primarily due to geography."""
    markers = (
        "Outside US",
        "No US location signal",
        "Not in job cities",
        "US-based but not job city",
    )
    return any(marker in reason for marker in markers)


def backfill_location_contacts(
    validated: list[DiscoveredContact],
    location_rejected: list[DiscoveredContact],
    *,
    min_target: int = _MIN_CONTACTS_TARGET,
    max_total: int | None = None,
) -> list[DiscoveredContact]:
    """When too few pass filters, add top location-rejected contacts back in."""
    if len(validated) >= min_target or not location_rejected:
        return validated

    final = list(validated)
    seen = {c.full_name.lower() for c in final if c.full_name}
    for contact in sorted(location_rejected, key=lambda c: c.relevance_score, reverse=True):
        if len(final) >= min_target:
            break
        if max_total is not None and len(final) >= max_total:
            break
        key = (contact.full_name or "").lower()
        if not key or key in seen:
            continue
        contact.metadata_json["validation"] = "passed (location backfill)"
        contact.metadata_json["location_backfill"] = True
        final.append(contact)
        seen.add(key)
    return final


def validate_contacts(
    contacts: list[DiscoveredContact],
    *,
    search_context: JobSearchContext,
    location_target: JobLocationTarget,
    job_title: str | None = None,
    min_valid: int = 1,
) -> dict[str, Any]:
    strict_cities = location_target.strict_cities
    dept_keywords = search_context.expanded_department_queries()

    validated: list[DiscoveredContact] = []
    rejected_reasons: list[str] = []
    location_rejected: list[DiscoveredContact] = []
    hm_without_dept = 0

    for contact in contacts:
        ok, reason = _contact_passes(
            contact,
            location_target=location_target,
            strict_cities=strict_cities,
            dept_keywords=dept_keywords,
            hm_without_dept=hm_without_dept,
            job_title=job_title,
        )
        if ok:
            contact.metadata_json["validation"] = "passed"
            validated.append(contact)
            if (
                dept_keywords
                and is_leadership_tier(contact.tier)
                and not person_matches_department(contact.title, dept_keywords)
            ):
                hm_without_dept += 1
        else:
            contact.metadata_json["validation"] = f"rejected: {reason}"
            rejected_reasons.append(f"{contact.full_name}: {reason}")
            if _is_location_rejection(reason):
                location_rejected.append(contact)

    return {
        "ok": len(validated) >= min_valid,
        "contacts": validated,
        "validated_count": len(validated),
        "rejected_count": len(contacts) - len(validated),
        "rejected_sample": rejected_reasons[:5],
        "location_rejected": location_rejected,
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
    hm_without_dept: int = 0,
    job_title: str | None = None,
) -> tuple[bool, str]:
    from openrole.scrapers.email_utils import is_placeholder_email

    if is_placeholder_email(contact.email):
        contact.email = None
        contact.metadata_json["email_placeholder"] = True

    if contact.relevance_score < _MIN_RELEVANCE:
        return False, "low relevance score"

    function_reason = wrong_function_for_engineering_job(contact.title, job_title=job_title)
    if function_reason:
        return False, function_reason

    loc_penalty, loc_reason = score_person_location(
        location=contact.location,
        title=contact.title,
        target=location_target,
    )
    if strict_cities and loc_penalty > _MAX_CITY_PENALTY:
        if loc_reason == "Location unknown" and loc_penalty <= _MAX_CITY_PENALTY_UNKNOWN:
            pass
        else:
            return False, loc_reason

    if dept_keywords:
        recruiters = contact.tier in (
            ContactTier.ROLE_RECRUITER,
            ContactTier.GENERAL_RECRUITER,
            ContactTier.CMU_ALUMNI,
        )
        hiring_manager = is_leadership_tier(contact.tier)
        in_dept = person_matches_department(contact.title, dept_keywords)
        is_ic_engineer = contact.tier == ContactTier.TEAM_ENGINEER or (
            _ENGINEERING_TITLE_SIGNAL_RE.search(contact.title or "")
            and not hiring_manager
            and not recruiters
        )
        if is_ic_engineer and contact.relevance_score >= 45:
            pass  # IC engineers OK for referral even if sub-team label differs (e.g. Music vs ML)
        elif not recruiters and not in_dept and not hiring_manager:
            if contact.relevance_score < _MIN_SCORE_WITHOUT_DEPT:
                return False, f"not in department ({', '.join(dept_keywords[:3])})"
        elif hiring_manager and not in_dept:
            if hm_without_dept >= _MAX_UNRELATED_HIRING_MANAGERS:
                return False, f"too many hiring managers outside {dept_keywords[0]}"

    llm_score = contact.metadata_json.get("llm_relevance")
    if llm_score is not None and int(llm_score) < 15:
        return False, "LLM marked irrelevant"

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
