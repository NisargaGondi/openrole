"""Rigorous scout filters: software roles + resume match + F-1/OPT eligibility."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

from openrole.agents.job_scorer import score_job_relevance
from openrole.agents.experience_fit import experience_fit, estimate_candidate_years_experience
from openrole.agents.resume_scout_profile import ScoutResumeProfile, job_matches_resume
from openrole.config import Settings, get_settings
from openrole.schemas.job import ParsedJob

_NON_SOFTWARE_TITLE = re.compile(
    r"\b("
    r"wealth|financial advisor|financial planner|portfolio|banker|teller|"
    r"nurse|registered nurse|\brn\b|\blpn\b|clinical|medical assistant|"
    r"pharmacist|physical therapist|dental|veterinary|"
    r"sales (?:rep|representative|associate|manager)|account executive|"
    r"marketing manager|brand manager|copywriter|"
    r"recruiter|talent acquisition|hr manager|human resources|"
    r"customer service|call center|warehouse|forklift|driver|delivery|"
    r"cashier|retail|store manager|"
    r"bookkeeper|accountant|auditor|tax preparer|paralegal|"
    r"underwriter|loan officer|mortgage|insurance agent|"
    r"property manager|real estate agent|leasing consultant|"
    r"chef|cook|server|bartender|housekeeper|care coordinator"
    r")\b",
    re.I,
)

_SOFTWARE_TITLE = re.compile(
    r"\b("
    r"software|swe|sde|developer|programmer|"
    r"(?:machine learning|ml|ai|data|security|cyber|cloud|platform|"
    r"backend|front[\s-]?end|full[\s-]?stack|infra|devops|site reliability|sre|"
    r"research|applied) engineer|"
    r"research scientist|applied scientist|scientist|"
    r"security researcher|penetration tester|"
    r"engineering intern|software intern"
    r")\b",
    re.I,
)

_OPT_POSITIVE = re.compile(
    r"(?:"
    r"\bstem opt\b|optional practical training|"
    r"\bcpt\b|curricular practical training|"
    r"\bwill sponsor\b|sponsorship (?:is )?available|"
    r"\bh-?1b sponsor(?:ship)?\b|"
    r"visa sponsorship (?:is )?available|"
    r"open to (?:international|f-?1) students|"
    r"eligible for (?:stem )?opt"
    r")",
    re.I,
)

_OPT_NEGATIVE = re.compile(
    r"(?:"
    r"\bno sponsorship\b|\bnot sponsor\b|cannot sponsor|unable to sponsor|will not sponsor|"
    r"\bwithout sponsorship\b|unsponsored|"
    r"without necessity for.{0,50}sponsor|"
    r"does not participate in.{0,60}(?:f-?1|stem opt)|"
    r"not participate in the f-?1 stem opt|"
    r"authorized to work.{0,80}without.{0,50}sponsor|"
    r"authorization to work.{0,80}without.{0,50}sponsor|"
    r"us citizen(?:ship)?(?: only| required)?|u\.s\. citizen(?:ship)?(?: only| required)?|"
    r"must be (?:a )?(?:u\.s\. |us )?citizen|"
    r"green card (?:required|only)|permanent resident(?: only| required)|"
    r"\bclearance required\b"
    r")",
    re.I,
)


class RejectReason(str, Enum):
    NOT_SOFTWARE = "not_software"
    RESUME_MISMATCH = "resume_mismatch"
    EXPERIENCE_MISMATCH = "experience_mismatch"
    OPT_INELIGIBLE = "opt_ineligible"
    OPT_UNKNOWN = "opt_unknown"
    # Back-compat alias
    WRONG_FIELD = "resume_mismatch"


@dataclass(frozen=True)
class ScoutJobVerdict:
    passed: bool
    relevance_score: int
    role_families: tuple[str, ...]  # matched resume skill highlights
    opt_status: str
    reject_reason: RejectReason | None = None
    match_hits: int = 0

    @property
    def reject_label(self) -> str | None:
        if self.reject_reason is None:
            return None
        return {
            RejectReason.NOT_SOFTWARE: "Not a software/tech role",
            RejectReason.RESUME_MISMATCH: "Does not match selected resume",
            RejectReason.EXPERIENCE_MISMATCH: "Requires more years of experience than you have",
            RejectReason.OPT_INELIGIBLE: "No visa sponsorship / OPT",
            RejectReason.OPT_UNKNOWN: "OPT/sponsorship not mentioned (required)",
        }[self.reject_reason]


def job_text_blob(parsed: ParsedJob) -> str:
    return " ".join(
        filter(
            None,
            [parsed.title, parsed.department, parsed.description, " ".join(parsed.locations or [])],
        )
    )


def assess_opt_status(text: str, parsed: ParsedJob | None = None) -> str:
    """OPT/sponsorship — LLM enrich, Handshake structured fields, then JD text."""
    if parsed and parsed.raw_payload:
        enrich = parsed.raw_payload.get("llm_enrich") or {}
        if isinstance(enrich, dict):
            visa_status = enrich.get("visa_status")
            if visa_status in ("eligible", "ineligible", "unknown"):
                return str(visa_status)
            if enrich.get("accepts_opt") or enrich.get("accepts_cpt") or enrich.get("will_sponsor"):
                return "eligible"
            if enrich.get("work_auth_us_only") is True:
                return "ineligible"

        meta = parsed.raw_payload.get("metadata") or {}
        if isinstance(meta, dict):
            if (
                meta.get("accepts_opt")
                or meta.get("will_sponsor")
                or meta.get("accepts_cpt")
                or meta.get("accepts_opt_candidates")
                or meta.get("accepts_cpt_candidates")
                or meta.get("willing_to_sponsor_candidate")
            ):
                return "eligible"
            if meta.get("work_auth_required") is True and meta.get("will_sponsor") is False:
                return "ineligible"

    from openrole.agents.scout_job_prepare import is_low_quality_job_description

    if is_low_quality_job_description(text):
        return "unknown"

    lower = text.lower()
    if _OPT_NEGATIVE.search(lower):
        return "ineligible"
    if _OPT_POSITIVE.search(lower):
        return "eligible"
    return "unknown"


def is_software_role(title: str, full_text: str) -> bool:
    title = title or ""
    if _NON_SOFTWARE_TITLE.search(title):
        return False
    if _SOFTWARE_TITLE.search(title):
        return True
    if re.search(r"\bengineer\b", title, re.I):
        tech_signals = (
            r"\b(python|java|javascript|typescript|c\+\+|kubernetes|aws|gcp|"
            r"distributed|api|microservice|git|ci/cd|software|machine learning|security)\b"
        )
        return bool(re.search(tech_signals, full_text, re.I))
    return False


def _scout_profile_from_context(profile: dict[str, Any]) -> ScoutResumeProfile | None:
    raw = profile.get("scout_resume_profile")
    if isinstance(raw, ScoutResumeProfile):
        return raw
    return None


def _candidate_years(
    profile: dict[str, Any],
    settings: Settings,
    scout_profile: ScoutResumeProfile | None,
) -> float:
    if settings.candidate_years_experience is not None:
        return float(settings.candidate_years_experience)
    for key in ("resume_text", "text"):
        raw = profile.get(key)
        if isinstance(raw, str) and raw.strip():
            return estimate_candidate_years_experience(raw)
    resumes = profile.get("resumes") or []
    if isinstance(resumes, list):
        for item in resumes:
            if isinstance(item, dict):
                text = item.get("text") or ""
                if text.strip():
                    return estimate_candidate_years_experience(text)
    if scout_profile:
        label = scout_profile.resume_label.lower()
        if "phd" in label:
            return 4.0
    return 2.0


def evaluate_scout_job(
    parsed: ParsedJob,
    *,
    profile: dict[str, Any],
    search_term: str | None = None,
    settings: Settings | None = None,
    skip_opt: bool = False,
) -> ScoutJobVerdict:
    """Gate jobs: software role + resume alignment + OPT (mandatory)."""
    settings = settings or get_settings()
    text = job_text_blob(parsed)
    title = parsed.title or ""
    lower = text.lower()

    relevance = score_job_relevance(parsed, profile=profile, search_term=search_term)

    if not is_software_role(title, lower):
        return ScoutJobVerdict(
            passed=False,
            relevance_score=relevance,
            role_families=(),
            opt_status=assess_opt_status(lower, parsed),
            reject_reason=RejectReason.NOT_SOFTWARE,
        )

    scout_profile = _scout_profile_from_context(profile)
    matched_terms: list[str] = []
    match_hits = 0
    if scout_profile is None:
        # No resume — allow only if relevance is already high
        if relevance < settings.scout_min_relevance_score:
            return ScoutJobVerdict(
                passed=False,
                relevance_score=relevance,
                role_families=(),
                opt_status=assess_opt_status(lower, parsed),
                reject_reason=RejectReason.RESUME_MISMATCH,
            )
    else:
        ok, match_hits, matched_terms = job_matches_resume(lower, title, scout_profile)
        if not ok:
            return ScoutJobVerdict(
                passed=False,
                relevance_score=relevance,
                role_families=tuple(matched_terms[:5]),
                opt_status=assess_opt_status(lower, parsed),
                reject_reason=RejectReason.RESUME_MISMATCH,
                match_hits=match_hits,
            )

        candidate_years = _candidate_years(profile, settings, scout_profile)
        if settings.scout_filter_experience:
            fits_exp, required_years, _ = experience_fit(
                job_text=lower,
                title=title,
                candidate_years=candidate_years,
                slack_years=float(settings.scout_experience_slack_years),
            )
            if not fits_exp and required_years is not None:
                return ScoutJobVerdict(
                    passed=False,
                    relevance_score=relevance,
                    role_families=tuple(matched_terms[:5]),
                    opt_status=assess_opt_status(lower, parsed),
                    reject_reason=RejectReason.EXPERIENCE_MISMATCH,
                    match_hits=match_hits,
                )

    opt_status = assess_opt_status(lower, parsed)
    if not skip_opt:
        if opt_status == "ineligible":
            return ScoutJobVerdict(
                passed=False,
                relevance_score=relevance,
                role_families=tuple(matched_terms[:5]),
                opt_status=opt_status,
                reject_reason=RejectReason.OPT_INELIGIBLE,
                match_hits=match_hits,
            )

        if settings.scout_require_opt_mention and opt_status == "unknown":
            return ScoutJobVerdict(
                passed=False,
                relevance_score=relevance,
                role_families=tuple(matched_terms[:5]),
                opt_status=opt_status,
                reject_reason=RejectReason.OPT_UNKNOWN,
                match_hits=match_hits,
            )

    return ScoutJobVerdict(
        passed=True,
        relevance_score=relevance,
        role_families=tuple(matched_terms[:8]),
        opt_status=opt_status,
        match_hits=match_hits,
    )


def default_scout_search_terms(profile: dict[str, Any], settings: Settings | None = None) -> list[str]:
    """Search terms derived from the selected resume (not hardcoded families)."""
    settings = settings or get_settings()
    scout = _scout_profile_from_context(profile)
    if scout and scout.search_terms:
        return list(scout.search_terms)

    custom = settings.scout_search_terms_list()
    if custom:
        return custom

    raw = (settings.candidate_role_search or "").strip()
    if raw:
        parts = [p.strip() for p in raw.replace(";", ",").split(",") if p.strip()]
        if parts:
            return parts[:6]

    return ["software engineer"]
