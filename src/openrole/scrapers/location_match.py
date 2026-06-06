"""Parse job locations and score contact geography vs posting."""

from __future__ import annotations

import re
from dataclasses import dataclass

_US_TOKENS = ("united states", "usa", "u.s.", "u.s.a", " us", " us,")
_US_STATE_ABBR = {
    "al", "ak", "az", "ar", "ca", "co", "ct", "de", "fl", "ga", "hi", "id", "il", "in", "ia",
    "ks", "ky", "la", "me", "md", "ma", "mi", "mn", "ms", "mo", "mt", "ne", "nv", "nh", "nj",
    "nm", "ny", "nc", "nd", "oh", "ok", "or", "pa", "ri", "sc", "sd", "tn", "tx", "ut", "vt",
    "va", "wa", "wv", "wi", "wy", "dc",
}
_NON_US_MARKERS = (
    "india", "israel", "china", "uk", "united kingdom", "germany", "france", "canada",
    "bangalore", "bengaluru", "hyderabad", "pune", "chennai", "mumbai", "delhi", "noida",
    "tel aviv", "europe", "apac", "emea", "latam",
)
_ACADEMIC_EMAIL_MARKERS = (".edu", ".ac.in", ".ac.uk", ".edu.in")


@dataclass(frozen=True)
class JobLocationTarget:
    """Normalized location intent from a job posting."""

    raw_locations: tuple[str, ...]
    us_only: bool
    apollo_person_locations: tuple[str, ...]
    city_tokens: tuple[str, ...]
    state_tokens: tuple[str, ...]
    strict_cities: bool = False


def parse_job_locations(locations: list[str] | None) -> JobLocationTarget:
    raw = tuple(loc.strip() for loc in (locations or []) if loc and str(loc).strip())
    us_only = _infer_us_only(raw)
    cities: list[str] = []
    states: list[str] = []
    apollo_locs: list[str] = []

    if us_only:
        apollo_locs.append("United States")

    for loc in raw:
        loc_l = loc.lower()
        city, state = _split_city_state(loc)
        if city:
            cities.append(city)
            if us_only and state:
                apollo_locs.append(f"{city.title()}, {state.upper()}, US")
            elif us_only:
                apollo_locs.append(f"{city.title()}, US")
        if state:
            states.append(state)

    # Dedupe while preserving order
    def _dedupe(items: list[str]) -> tuple[str, ...]:
        seen: set[str] = set()
        out: list[str] = []
        for item in items:
            key = item.lower()
            if key not in seen:
                seen.add(key)
                out.append(item)
        return tuple(out)

    return JobLocationTarget(
        raw_locations=raw,
        us_only=us_only,
        apollo_person_locations=_dedupe(apollo_locs) or (("United States",) if us_only else ()),
        city_tokens=tuple(c.lower() for c in _dedupe(cities)),
        state_tokens=tuple(s.lower() for s in _dedupe(states)),
    )


def score_person_location(
    *,
    location: str | None,
    title: str | None,
    target: JobLocationTarget,
) -> tuple[int, str]:
    """0 = best match, higher = worse. Returns (penalty_points, reason)."""
    blob = " ".join(p for p in (location, title) if p).lower()
    if not blob:
        return (40 if target.us_only else 15, "Location unknown")

    if target.us_only and _mentions_non_us(blob):
        if "india" in blob:
            return (200, "Outside US — India (low outreach value for US role)")
        return (150, "Outside US — does not match posting geography")

    if target.us_only and not _mentions_us(blob):
        return (80, "No US location signal")

    if target.city_tokens or target.state_tokens:
        for city in target.city_tokens:
            if city in blob:
                return (0, f"Matches job city ({city.title()})")
        for state in target.state_tokens:
            if re.search(rf"\b{re.escape(state)}\b", blob):
                return (5, f"Matches job state ({state.upper()})")
        if target.strict_cities:
            return (120, f"Not in job cities ({', '.join(c.title() for c in target.city_tokens)})")
        if target.us_only and _mentions_us(blob):
            return (25, "US-based but not job city/state")

    if target.us_only and _mentions_us(blob):
        return (10, "United States")

    return (20, "Location partial match")


def person_matches_department(title: str | None, keywords: list[str]) -> bool:
    if not keywords:
        return True
    title_l = (title or "").lower()
    return any(kw.lower() in title_l for kw in keywords)


def email_actionable(*, email: str | None, company_domain: str | None) -> tuple[bool, str]:
    if not email:
        return False, "No email"
    domain = email.split("@")[-1].lower().strip()
    if any(marker in domain for marker in _ACADEMIC_EMAIL_MARKERS):
        return False, f"Non-company email ({domain})"
    if company_domain and (domain == company_domain or domain.endswith(f".{company_domain}")):
        return True, f"Company email (@{domain})"
    if company_domain:
        return False, f"Email not at @{company_domain}"
    return True, f"Email (@{domain})"


def _infer_us_only(locations: tuple[str, ...]) -> bool:
    if not locations:
        return True  # default US full-time search
    for loc in locations:
        loc_l = loc.lower()
        if any(tok in loc_l for tok in _US_TOKENS):
            return True
        if re.search(r",\s*[a-z]{2}\b", loc_l):
            state = loc_l.rsplit(",", 1)[-1].strip()[:2]
            if state in _US_STATE_ABBR:
                return True
        if "remote" in loc_l and ("us" in loc_l or "usa" in loc_l or "united states" in loc_l):
            return True
    if all(_mentions_non_us(loc.lower()) for loc in locations):
        return False
    return True


def _split_city_state(loc: str) -> tuple[str | None, str | None]:
    loc = loc.strip()
    if not loc:
        return None, None
    if "," in loc:
        left, right = loc.rsplit(",", 1)
        city = left.strip()
        state = right.strip().split()[0][:2].lower()
        if state in _US_STATE_ABBR:
            return city, state
        return city, None
    return loc, None


def _mentions_us(text: str) -> bool:
    if any(tok in text for tok in _US_TOKENS):
        return True
    for state in _US_STATE_ABBR:
        if re.search(rf"\b{re.escape(state)}\b", text):
            return True
    if "california" in text or "texas" in text or "new york" in text:
        return True
    return False


def _mentions_non_us(text: str) -> bool:
    return any(marker in text for marker in _NON_US_MARKERS)
