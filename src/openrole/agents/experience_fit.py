"""Parse JD experience requirements and compare to candidate years."""

from __future__ import annotations

import re

_YEARS_PATTERNS = (
    re.compile(
        r"(\d+)\+?\s*(?:years?|yrs?)\s+(?:of\s+)?"
        r"(?:professional\s+|relevant\s+|industry\s+|work\s+|technical\s+)?(?:engineering\s+)?(?:experience|exp)\b",
        re.I,
    ),
    re.compile(r"(?:minimum|min\.|at least|required)\s+(\d+)\+?\s*(?:years?|yrs?)\b", re.I),
    re.compile(r"(\d+)\+?\s*(?:years?|yrs?)\s+(?:in|with|building|developing|technical)\b", re.I),
)

_TITLE_FLOOR: tuple[tuple[re.Pattern[str], int], ...] = (
    (re.compile(r"\bdistinguished\b", re.I), 10),
    (re.compile(r"\b(?:sr\.?|senior)\s+principal\b", re.I), 8),
    (re.compile(r"\bprincipal\b", re.I), 6),
    (re.compile(r"\bstaff\b", re.I), 5),
    (re.compile(r"\b(?:sr\.?|senior)\s+(?:software|ml|ai|data|security)\b", re.I), 4),
    (re.compile(r"\b(?:sr\.?|senior)\s+(?:engineer|developer|scientist)\b", re.I), 4),
)


def title_experience_floor(title: str) -> int:
    """Conservative minimum years implied by job title alone."""
    for pattern, years in _TITLE_FLOOR:
        if pattern.search(title or ""):
            return years
    return 0


def parse_required_experience_years(text: str, title: str = "") -> int | None:
    """Best estimate of years of experience the role expects (max of JD signals + title floor)."""
    found: list[int] = []
    for pattern in _YEARS_PATTERNS:
        for match in pattern.finditer(text or ""):
            try:
                value = int(match.group(1))
            except (TypeError, ValueError):
                continue
            if 1 <= value <= 25:
                found.append(value)

    floor = title_experience_floor(title)
    if found:
        explicit = max(found)
        return max(explicit, floor) if floor else explicit
    return floor if floor else None


def estimate_candidate_years_experience(resume_text: str) -> float:
    """Rough YOE from resume text for students / early-career (not calendar-perfect)."""
    lower = (resume_text or "").lower()
    if not lower.strip():
        return 1.0

    internships = len(re.findall(r"\bintern(ship)?\b", lower))
    fulltime_signals = len(
        re.findall(
            r"\b(software|research|machine learning|security|data)\s+(engineer|developer|scientist)\b",
            lower,
        )
    )
    recent = 1 if re.search(r"\b(20(24|25|26)|present|current)\b", lower) else 0

    estimate = 0.5 * internships + 0.8 * min(fulltime_signals, 2) + 0.5 * recent
    return max(0.5, min(estimate, 4.0))


def experience_fit(
    *,
    job_text: str,
    title: str,
    candidate_years: float,
    slack_years: float = 1.0,
) -> tuple[bool, int | None, float]:
    """
    Return (fits, required_years, candidate_years).
    Passes when required is unknown or candidate_years + slack >= required.
    """
    required = parse_required_experience_years(job_text, title)
    if required is None:
        return True, None, candidate_years
    fits = candidate_years + slack_years >= required
    return fits, required, candidate_years
