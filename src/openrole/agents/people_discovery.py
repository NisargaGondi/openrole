"""Discover and rank contacts at a job's company via Apollo.io."""

from __future__ import annotations

import re
from dataclasses import asdict
from typing import Any

from sqlalchemy import select

from openrole.agents.contact_validation import build_location_target, validate_contacts
from openrole.agents.job_context import build_job_search_context
from openrole.config import get_settings
from openrole.db.models import Company, Contact, Job
from openrole.db.repository import save_discovered_contacts
from openrole.db.session import session_scope
from openrole.schemas.contact import ContactTier, DiscoveredContact, compute_discovery_source
from openrole.schemas.job_context import JobSearchContext
from openrole.scrapers.location_match import (
    JobLocationTarget,
    email_actionable,
    parse_job_locations,
    person_matches_department,
    score_person_location,
)
from openrole.scrapers import careershift_client
from openrole.scrapers.careershift_validate import merge_validated_fields, validate_careershift_contact
from openrole.tools import apollo_client
from openrole.tools.domain_resolver import resolve_company_domain

_MAX_CONTACTS = 15
_ENRICH_LIMIT = 12
_EXCLUDE_RELEVANCE_BELOW = 20

_SEARCH_PASSES: list[tuple[str, list[str]]] = [
    ("managers", ["hiring manager", "engineering manager", "director", "head of"]),
    ("recruiters", ["recruiter", "talent acquisition", "technical recruiter", "sourcer"]),
    ("engineers", ["software engineer", "machine learning engineer", "research engineer"]),
]

_CMU_SCHOOL_KEYWORDS = ("carnegie mellon", "cmu")

_MANAGER_RE = re.compile(
    r"\b(hiring manager|engineering manager|eng\.? manager|"
    r"software engineering manager|director(?!,?\s*talent)|head of|"
    r"\bvp\b|vice president)\b",
    re.I,
)
_RECRUITER_RE = re.compile(
    r"\b(recruiter|talent acquisition|sourcer|staffing|campus recruiter|university relations)\b",
    re.I,
)
_ENGINEER_RE = re.compile(
    r"\b(engineer|developer|scientist|researcher|architect)\b",
    re.I,
)
_INDIA_TITLE_RE = re.compile(r"\bindia\b|\(india\)", re.I)


class PeopleDiscoveryError(Exception):
    pass


def extract_context_for_job(job_id: str) -> tuple[JobSearchContext, JobLocationTarget, list[str]]:
    """LangGraph node: derive location + department filters from job."""
    with session_scope() as session:
        job = _load_job(session, job_id)
        ctx = build_job_search_context(job)
        loc = build_location_target(ctx)
        warnings: list[str] = []
        if not ctx.office_locations:
            warnings.append("No office cities extracted — add locations on re-ingest or paste JD.")
        if not ctx.apollo_department_queries():
            warnings.append("No department/team extracted — people search may be broader.")
        else:
            warnings.append(f"Department filter: {', '.join(ctx.apollo_department_queries()[:4])}")
        if loc.strict_cities:
            warnings.append(
                "City-strict mode: " + ", ".join(c.title() for c in loc.city_tokens)
            )
        return ctx, loc, warnings


def rank_people_candidates(
    job_id: str,
    *,
    search_context: JobSearchContext,
    location_target: JobLocationTarget,
) -> tuple[list[DiscoveredContact], str, str, list[str]]:
    """LangGraph node: Apollo + CareerShift search + ranking (no persist)."""
    extra_warnings: list[str] = []
    with session_scope() as session:
        job = _load_job(session, job_id)
        company = _load_company(session, job)
        domain = _resolve_domain(company, job) or ""
        if not domain:
            resolution = resolve_company_domain(
                company_name=company.name,
                existing_domain=company.domain,
                source_url=job.source_url,
                description=job.description,
                raw_payload=job.raw_payload,
            )
            if resolution:
                domain = resolution.domain
                company.domain = domain
                session.commit()
                extra_warnings.append(
                    f"Resolved company domain `{domain}` via {resolution.source} ({resolution.confidence})."
                )
            elif apollo_client.is_configured():
                raise PeopleDiscoveryError(
                    f"No company domain for {company.name}. "
                    "Set domain on the Saved jobs page or re-ingest with a clearer posting."
                )

        raw: list[dict[str, Any]] = []
        if apollo_client.is_configured():
            if not domain:
                extra_warnings.append("Apollo skipped — no company domain.")
            else:
                try:
                    org = apollo_client.enrich_organization(domain=domain)
                    if org.get("id") and not company.apollo_organization_id:
                        company.apollo_organization_id = str(org["id"])
                        session.commit()
                    raw = _collect_people(domain, location_target, search_context=search_context)
                    raw.extend(_search_cmu_alumni(domain, location_target))
                except apollo_client.ApolloError:
                    extra_warnings.append(f"Apollo enrich/search failed for {domain}")
        else:
            extra_warnings.append("Apollo not configured — using CareerShift only.")

        cs_people, cs_warnings = _collect_people_careershift(
            company.name,
            location_target,
            search_context=search_context,
            company_domain=domain or None,
        )
        raw.extend(cs_people)
        extra_warnings.extend(cs_warnings)

        if not raw:
            raise PeopleDiscoveryError(
                "No people sources available. Set APOLLO_API_KEY and/or log in to CareerShift."
            )

        ranked = _rank_contacts(
            raw,
            job=job,
            company_name=company.name,
            company_domain=domain,
            location_target=location_target,
            search_context=search_context,
        )
        ranked = [c for c in ranked if c.relevance_score >= _EXCLUDE_RELEVANCE_BELOW]
        ranked.sort(key=lambda c: c.relevance_score, reverse=True)
        return ranked, domain, company.name, extra_warnings


def validate_and_finalize_contacts(
    candidates: list[DiscoveredContact],
    *,
    search_context: JobSearchContext,
    location_target: JobLocationTarget,
    company_domain: str,
) -> tuple[list[DiscoveredContact], dict[str, Any], list[str]]:
    """Validate filters; enrich before validation so Apollo locations are available."""
    warnings: list[str] = []

    # Enrich top pool first — search results often omit city until match_person.
    pool = sorted(candidates, key=lambda c: c.relevance_score, reverse=True)[:30]
    if company_domain and pool:
        _enrich_contacts(pool, company_domain=company_domain, limit=_ENRICH_LIMIT)
        _refresh_contact_reasons(
            pool,
            search_context=search_context,
            location_target=location_target,
            company_domain=company_domain,
        )

    validation = validate_contacts(
        pool,
        search_context=search_context,
        location_target=location_target,
    )
    final = validation["contacts"]

    if validation.get("retry_suggestion") == "relax_city_filter" and location_target.strict_cities:
        relaxed = JobLocationTarget(
            raw_locations=location_target.raw_locations,
            us_only=location_target.us_only,
            apollo_person_locations=location_target.apollo_person_locations,
            city_tokens=location_target.city_tokens,
            state_tokens=location_target.state_tokens,
            strict_cities=False,
        )
        validation = validate_contacts(
            pool,
            search_context=search_context,
            location_target=relaxed,
        )
        final = validation["contacts"]
        warnings.append("Relaxed city filter — kept US matches when strict city match was empty.")

    if not validation["ok"]:
        warnings.append(
            f"Only {validation['validated_count']} contacts passed location/department filters."
        )

    final = final[:_MAX_CONTACTS]
    final.sort(key=_sort_key, reverse=True)
    for idx, contact in enumerate(final, start=1):
        contact.priority_rank = idx

    return final, validation, warnings


def _refresh_contact_reasons(
    contacts: list[DiscoveredContact],
    *,
    search_context: JobSearchContext,
    location_target: JobLocationTarget,
    company_domain: str | None = None,
) -> None:
    dept_keywords = search_context.apollo_department_queries()
    for contact in contacts:
        tier_name = contact.tier.name if hasattr(contact.tier, "name") else str(contact.tier)
        tier_label = tier_name.replace("_", " ").title()
        loc_penalty, loc_reason = score_person_location(
            location=contact.location,
            title=contact.title,
            target=location_target,
        )
        _ = loc_penalty
        parts = [tier_label]
        if loc_reason and loc_reason != "Location unknown":
            parts.append(loc_reason)
        if person_matches_department(contact.title, dept_keywords):
            parts.append(f"Department match ({search_context.department_name or dept_keywords[0]})")
        if contact.email:
            _, email_reason = email_actionable(
                email=contact.email,
                company_domain=company_domain,
            )
            parts.append(email_reason)
        elif (contact.metadata_json or {}).get("stored_email_raw"):
            parts.append("No company email")
        elif (contact.metadata_json or {}).get("needs_email"):
            parts.append("Email pending — CareerShift detail fetch")
        contact.priority_reason = " · ".join(dict.fromkeys(p for p in parts if p))
        contact.metadata_json["location_reason"] = loc_reason


def discover_people_for_job(
    job_id: str,
    *,
    enrich_top_n: int = _ENRICH_LIMIT,
) -> dict[str, Any]:
    """Full pipeline: context → search → validate → persist (UI entry point)."""
    if not apollo_client.is_configured() and not careershift_client.is_ready():
        raise PeopleDiscoveryError(
            "People discovery needs APOLLO_API_KEY and/or CareerShift login "
            "(python scripts/careershift_login.py)."
        )

    ctx, loc, ctx_warnings = extract_context_for_job(job_id)
    candidates, domain, company_name, source_warnings = rank_people_candidates(
        job_id, search_context=ctx, location_target=loc
    )
    final, validation, val_warnings = validate_and_finalize_contacts(
        candidates,
        search_context=ctx,
        location_target=loc,
        company_domain=domain,
    )
    _ = enrich_top_n  # enrich handled in validate_and_finalize_contacts

    with session_scope() as session:
        job = _load_job(session, job_id)
        company = _load_company(session, job)
        saved = save_discovered_contacts(
            session,
            company_id=company.id,
            contacts=final,
            source_job_id=job_id,
        )
        session.commit()

    all_warnings = ctx_warnings + source_warnings + val_warnings + _discovery_warnings(domain, final, loc)
    return {
        "status": "ok" if final else "partial",
        "job_id": job_id,
        "company_name": company_name,
        "domain": domain,
        "contact_count": len(saved),
        "contacts": [_contact_summary(x) for x in saved],
        "search_context": ctx.model_dump(),
        "location_filter": list(loc.apollo_person_locations),
        "validation": {
            "validated_count": validation.get("validated_count"),
            "rejected_count": validation.get("rejected_count"),
            "department_keywords": validation.get("department_keywords"),
        },
        "warnings": all_warnings,
    }


def list_contacts_for_job(job_id: str) -> list[Contact]:
    with session_scope() as session:
        job = session.scalar(select(Job).where(Job.id == job_id).limit(1))
        if job is None or not job.company_id:
            return []
        return list(
            session.scalars(
                select(Contact)
                .where(Contact.company_id == job.company_id)
                .order_by(Contact.priority_rank.asc(), Contact.full_name.asc())
            )
        )


def _load_job(session, job_id: str) -> Job:
    job = session.scalar(select(Job).where(Job.id == job_id).limit(1))
    if job is None:
        raise PeopleDiscoveryError(f"Job not found: {job_id}")
    return job


def _load_company(session, job: Job) -> Company:
    company = session.scalar(select(Company).where(Company.id == job.company_id).limit(1))
    if company is None:
        raise PeopleDiscoveryError("Job has no linked company")
    return company


def _resolve_domain(company: Company, job: Job) -> str | None:
    if company.domain:
        return apollo_client.normalize_domain(company.domain)
    raw = job.raw_payload or {}
    meta = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
    for candidate in (meta.get("company_domain"), raw.get("company_domain")):
        if candidate:
            return apollo_client.normalize_domain(str(candidate))
    dr = raw.get("domain_resolution") if isinstance(raw.get("domain_resolution"), dict) else {}
    if dr.get("domain"):
        return apollo_client.normalize_domain(str(dr["domain"]))
    resolution = resolve_company_domain(
        company_name=company.name,
        source_url=job.source_url,
        description=job.description,
        raw_payload=raw if isinstance(raw, dict) else None,
    )
    return resolution.domain if resolution else None


def _collect_people(
    domain: str,
    location_target: JobLocationTarget,
    *,
    search_context: JobSearchContext,
) -> list[dict[str, Any]]:
    seen: set[str] = set()
    merged: list[dict[str, Any]] = []
    apollo_locs = list(location_target.apollo_person_locations) or None
    dept_queries = search_context.apollo_department_queries()

    for _label, titles in _SEARCH_PASSES:
        search_titles = list(titles)
        for dq in dept_queries[:2]:
            if dq.lower() not in " ".join(search_titles).lower():
                search_titles.append(dq)
        _merge_batch(
            merged,
            seen,
            apollo_client.search_people(
                domain=domain,
                person_titles=search_titles,
                person_locations=apollo_locs,
                per_page=12,
            ),
        )

    for dq in dept_queries[:3]:
        _merge_batch(
            merged,
            seen,
            apollo_client.search_people(
                domain=domain,
                q_keywords=dq,
                person_locations=apollo_locs,
                per_page=10,
            ),
        )

    if search_context.role_family:
        _merge_batch(
            merged,
            seen,
            apollo_client.search_people(
                domain=domain,
                q_keywords=search_context.role_family,
                person_locations=apollo_locs,
                per_page=10,
            ),
        )

    return merged


def _collect_people_careershift(
    company_name: str,
    location_target: JobLocationTarget,
    *,
    search_context: JobSearchContext,
    company_domain: str | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """CareerShift contact search passes (requires local login session)."""
    warnings: list[str] = []
    if not careershift_client.is_ready():
        return [], warnings

    settings = get_settings()
    # Company-only search; city/title filtering happens in OpenRole validation.
    queries: list[dict[str, Any]] = [
        {
            "company_name": company_name,
            "max_results": 40,
        }
    ]

    if settings.cmu_school_name:
        queries.append(
            {
                "company_name": company_name,
                "school_name": settings.cmu_school_name,
                "max_results": 15,
            }
        )

    try:
        merged = careershift_client.search_contacts_batch(queries)
    except careershift_client.CareerShiftNotConfiguredError:
        return [], warnings
    except careershift_client.CareerShiftSessionError as exc:
        warnings.append(str(exc))
        return [], warnings
    except careershift_client.CareerShiftSearchError as exc:
        warnings.append(f"CareerShift: {exc}")
        return [], warnings
    except Exception as exc:
        warnings.append(f"CareerShift: {type(exc).__name__}: {exc}")
        return [], warnings

    validated_people: list[dict[str, Any]] = []
    rejected = 0
    for person in merged:
        ok, reason, fields = validate_careershift_contact(
            person,
            company_name=company_name,
            company_domain=company_domain,
        )
        if not ok:
            rejected += 1
            continue
        person = merge_validated_fields(person, fields)
        if person.get("school") or person.get("_openrole_alumni_search"):
            person["_openrole_alumni_search"] = True
        validated_people.append(person)

    if rejected:
        warnings.append(f"CareerShift validation rejected {rejected} contacts.")

    if validated_people:
        warnings.append(f"CareerShift added {len(validated_people)} contact candidates.")
    elif queries:
        warnings.append(
            f"CareerShift returned no valid contacts for {company_name} "
            "(company-only search — filters applied after merge)."
        )
    return validated_people, warnings


def _careershift_location_string(location_target: JobLocationTarget) -> str | None:
    if location_target.city_tokens and location_target.state_tokens:
        city = location_target.city_tokens[0].replace("-", " ").title()
        state = location_target.state_tokens[0].upper()
        return f"{city}, {state}"
    if location_target.apollo_person_locations:
        return location_target.apollo_person_locations[0]
    return None


def _person_fields(raw: dict[str, Any]) -> dict[str, Any]:
    if raw.get("_openrole_careershift"):
        return careershift_client.person_to_fields(raw)
    return apollo_client.person_to_fields(raw)


def _merge_batch(merged: list, seen: set[str], batch: list[dict[str, Any]]) -> None:
    for person in batch:
        pid = person.get("id")
        if pid and pid in seen:
            continue
        if pid:
            seen.add(pid)
        merged.append(person)


def _search_cmu_alumni(domain: str, location_target: JobLocationTarget) -> list[dict[str, Any]]:
    settings = get_settings()
    apollo_locs = list(location_target.apollo_person_locations) or None
    try:
        people = apollo_client.search_people(
            domain=domain,
            q_keywords=settings.cmu_school_name,
            person_locations=apollo_locs,
            per_page=8,
        )
    except apollo_client.ApolloError:
        return []
    for person in people:
        person["_openrole_alumni_search"] = True
    return people


def _rank_contacts(
    raw_people: list[dict[str, Any]],
    *,
    job: Job,
    company_name: str,
    company_domain: str,
    location_target: JobLocationTarget,
    search_context: JobSearchContext,
) -> list[DiscoveredContact]:
    settings = get_settings()
    job_title = (job.title or "").lower()
    dept_keywords = search_context.apollo_department_queries()
    department = (search_context.department_name or job.department or "").lower()

    contacts: list[DiscoveredContact] = []
    seen_ids: set[str] = set()
    seen_emails: dict[str, int] = {}
    seen_linkedin: dict[str, int] = {}

    for raw in raw_people:
        fields = _person_fields(raw)
        pid = raw.get("id") or fields.get("apollo_person_id")
        if pid and pid in seen_ids:
            continue
        if pid:
            seen_ids.add(str(pid))

        title = fields.get("title") or ""
        tier, tier_reason = _classify_tier(
            title=title,
            person=raw,
            job_title=job_title,
            department=department,
            dept_keywords=dept_keywords,
            company_name=company_name,
            cmu_domain=settings.cmu_email_domain,
        )
        loc_penalty, loc_reason = score_person_location(
            location=fields.get("location"),
            title=title,
            target=location_target,
        )
        dept_bonus = _department_bonus(title, department, dept_keywords, job_title)
        dept_match = person_matches_department(title, dept_keywords)
        email_ok, email_reason = email_actionable(
            email=fields.get("email"),
            company_domain=company_domain,
        )

        relevance = 1000
        relevance -= int(tier) * 120
        relevance -= loc_penalty
        relevance += dept_bonus
        if dept_match:
            relevance += 45
        elif dept_keywords and tier not in (
            ContactTier.ROLE_RECRUITER,
            ContactTier.GENERAL_RECRUITER,
        ):
            relevance -= 60
        relevance += 40 if email_ok else -30
        if fields.get("linkedin_url"):
            relevance += 15
        if raw.get("has_email") and not fields.get("email"):
            relevance += 10

        reasons = [tier_reason, loc_reason]
        if dept_match:
            reasons.append(f"Department match ({search_context.department_name or dept_keywords[0]})")
        if email_reason:
            reasons.append(email_reason)

        is_careershift = bool(raw.get("_openrole_careershift"))
        meta = {
            "apollo_search": not is_careershift,
            "careershift_search": is_careershift,
            "careershift_contact_id": fields.get("careershift_id"),
            "has_email_flag": raw.get("has_email"),
            "email_actionable": email_ok,
            "location_reason": loc_reason,
            "department_match": dept_match,
            "company_domain": company_domain or None,
            "stored_email_raw": fields.get("email") if not email_ok else None,
            "needs_email": is_careershift and not fields.get("email"),
        }
        if not is_careershift and fields.get("apollo_person_id"):
            meta["apollo_person_id"] = fields.get("apollo_person_id")
        meta["discovery_source"] = compute_discovery_source(meta)

        email_key = (fields.get("email") or "").strip().lower()
        linkedin_key = _normalize_linkedin(fields.get("linkedin_url"))
        dup_idx = None
        if email_key and email_key in seen_emails:
            dup_idx = seen_emails[email_key]
        elif linkedin_key and linkedin_key in seen_linkedin:
            dup_idx = seen_linkedin[linkedin_key]
        if dup_idx is not None:
            _merge_duplicate_contact(
                contacts[dup_idx],
                raw=raw,
                fields=fields,
                is_careershift=is_careershift,
                relevance=relevance,
            )
            continue
        if email_key:
            seen_emails[email_key] = len(contacts)
        if linkedin_key:
            seen_linkedin[linkedin_key] = len(contacts)

        contacts.append(
            DiscoveredContact(
                full_name=fields["full_name"],
                title=title or None,
                email=fields["email"] if email_ok else None,
                linkedin_url=fields.get("linkedin_url"),
                location=fields.get("location"),
                apollo_person_id=fields.get("apollo_person_id") if not is_careershift else None,
                tier=tier,
                priority_rank=0,
                priority_reason=" · ".join(r for r in reasons if r),
                relevance_score=relevance,
                is_cmu_alumni=tier == ContactTier.CMU_ALUMNI,
                metadata_json=meta,
            )
        )

    return contacts


def _normalize_linkedin(url: str | None) -> str | None:
    if not url:
        return None
    u = url.strip().lower().split("?")[0].rstrip("/")
    if "linkedin.com/in/" in u:
        return u.split("linkedin.com/in/")[-1][:80]
    return u or None


def _merge_duplicate_contact(
    existing: DiscoveredContact,
    *,
    raw: dict[str, Any],
    fields: dict[str, Any],
    is_careershift: bool,
    relevance: int,
) -> None:
    existing.metadata_json["apollo_search"] = (
        existing.metadata_json.get("apollo_search") or not is_careershift
    )
    existing.metadata_json["careershift_search"] = (
        existing.metadata_json.get("careershift_search") or is_careershift
    )
    if is_careershift and fields.get("careershift_id"):
        existing.metadata_json["careershift_contact_id"] = fields.get("careershift_id")
    if not is_careershift and fields.get("apollo_person_id"):
        existing.apollo_person_id = fields.get("apollo_person_id")
        existing.metadata_json["apollo_person_id"] = fields.get("apollo_person_id")
    if fields.get("email") and not existing.email:
        existing.email = fields.get("email")
    if fields.get("location") and not existing.location:
        existing.location = fields.get("location")
    if fields.get("linkedin_url") and not existing.linkedin_url:
        existing.linkedin_url = fields.get("linkedin_url")
    existing.metadata_json["discovery_source"] = compute_discovery_source(existing.metadata_json)
    if relevance > existing.relevance_score:
        existing.relevance_score = relevance


def _classify_tier(
    *,
    title: str,
    person: dict[str, Any],
    job_title: str,
    department: str,
    dept_keywords: list[str],
    company_name: str,
    cmu_domain: str,
) -> tuple[ContactTier, str]:
    title_l = title.lower()

    if _INDIA_TITLE_RE.search(title_l) and "united states" not in title_l:
        return ContactTier.OTHER, "Role based outside US (India in title)"

    if _is_cmu_alumni(person, cmu_domain=cmu_domain):
        return ContactTier.CMU_ALUMNI, "CMU alumni at company"

    if _is_hiring_manager_title(title_l):
        if any(x in title_l for x in ("marketing", "sales application", "talent acquisition ( india)")):
            if _RECRUITER_RE.search(title_l):
                return ContactTier.GENERAL_RECRUITER, "Company recruiter"
            return ContactTier.OTHER, "Director outside hiring team"
        if person_matches_department(title, dept_keywords):
            return ContactTier.HIRING_MANAGER, f"Hiring manager in {department or 'target team'}"
        return ContactTier.HIRING_MANAGER, "Engineering manager / director"

    if _RECRUITER_RE.search(title_l):
        if "technical" in title_l or person_matches_department(title, dept_keywords):
            return ContactTier.ROLE_RECRUITER, "Technical / team recruiter"
        return ContactTier.GENERAL_RECRUITER, "Company recruiter"

    if _ENGINEER_RE.search(title_l):
        return ContactTier.TEAM_ENGINEER, "Engineer (referral path)"

    if person.get("_openrole_alumni_search"):
        return ContactTier.CMU_ALUMNI, f"CMU alumni search hit at {company_name}"

    return ContactTier.OTHER, "Related contact"


def _is_hiring_manager_title(title_l: str) -> bool:
    if _ENGINEER_RE.search(title_l) and not re.search(
        r"\b(manager|director|head of|vp)\b", title_l
    ):
        return False
    return bool(_MANAGER_RE.search(title_l))


def _department_bonus(
    title: str,
    department: str,
    dept_keywords: list[str],
    job_title: str,
) -> int:
    title_l = title.lower()
    bonus = 0
    if person_matches_department(title, dept_keywords):
        bonus += 55
    elif department and department in title_l:
        bonus += 40
    job_words = [w for w in re.split(r"[\s,/\-]+", job_title) if len(w) > 4]
    if sum(1 for w in job_words[:4] if w in title_l) >= 2:
        bonus += 15
    return bonus


def _is_cmu_alumni(person: dict[str, Any], *, cmu_domain: str) -> bool:
    if person.get("_openrole_alumni_search"):
        return True
    for key in ("education", "educations", "schools"):
        entries = person.get(key)
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            school = str(entry.get("school_name") or entry.get("organization_name") or "").lower()
            if any(kw in school for kw in _CMU_SCHOOL_KEYWORDS):
                return True
    email = str(person.get("email") or "").lower()
    if email.endswith(f"@{cmu_domain}"):
        return True
    school = str(person.get("school") or "").lower()
    if school and any(kw in school for kw in _CMU_SCHOOL_KEYWORDS):
        return True
    return False


def _enrich_contacts(
    contacts: list[DiscoveredContact],
    *,
    company_domain: str,
    limit: int,
) -> None:
    attempts = 0
    for contact in contacts:
        if attempts >= limit:
            break
        if contact.email:
            continue
        if not contact.apollo_person_id:
            continue
        attempts += 1
        try:
            enriched = apollo_client.match_person(apollo_id=contact.apollo_person_id)
        except apollo_client.ApolloError:
            continue
        fields = apollo_client.person_to_fields(enriched)
        email = fields.get("email")
        ok, email_reason = email_actionable(email=email, company_domain=company_domain)
        if ok and email:
            contact.email = email
            contact.relevance_score += 35
            contact.metadata_json["enriched"] = True
            contact.metadata_json["email_actionable"] = True
            contact.metadata_json["needs_email"] = False
        elif email:
            contact.metadata_json["stored_email_raw"] = email
            contact.metadata_json["email_actionable"] = False
        if fields.get("linkedin_url"):
            contact.linkedin_url = fields["linkedin_url"]
        if fields.get("location"):
            contact.location = fields["location"]
        if fields.get("full_name") and "Unknown" not in fields["full_name"]:
            contact.full_name = fields["full_name"]


def _sort_key(contact: DiscoveredContact) -> tuple:
    email_ok = contact.metadata_json.get("email_actionable") or bool(contact.email)
    dept = 1 if contact.metadata_json.get("department_match") else 0
    return (contact.relevance_score, 1 if email_ok else 0, dept, -int(contact.tier))


def _discovery_warnings(
    domain: str,
    contacts: list[DiscoveredContact],
    location_target: JobLocationTarget,
) -> list[str]:
    warnings: list[str] = []
    if not contacts:
        warnings.append(f"No validated contacts for {domain}.")
    elif location_target.strict_cities:
        warnings.append(
            "City-strict: " + ", ".join(c.title() for c in location_target.city_tokens)
        )
    with_email = sum(1 for c in contacts if c.email)
    if contacts and with_email == 0:
        warnings.append("No company emails — use LinkedIn or re-run after Apollo credits refresh.")
    return warnings


def _contact_summary(contact: Contact) -> dict[str, Any]:
    return {
        "id": contact.id,
        "full_name": contact.full_name,
        "title": contact.title,
        "email": contact.email,
        "linkedin_url": contact.linkedin_url,
        "priority_rank": contact.priority_rank,
        "priority_reason": contact.priority_reason,
    }


def location_target_to_dict(target: JobLocationTarget) -> dict[str, Any]:
    return asdict(target)


def location_target_from_dict(data: dict[str, Any]) -> JobLocationTarget:
    return JobLocationTarget(**data)
