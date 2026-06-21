"""ATS company rotation and scout memory helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from openrole.db.models import Company

_TIER_ORDER = {"ambitious": 0, "moderate": 1, "safe": 2}
_JUNK_COMPANY_NAMES = frozenset({"acme", "acme corp", "acme ai", "example", "test co"})


def company_has_ats_metadata(meta: dict[str, Any] | None) -> bool:
    m = meta or {}
    return bool(
        m.get("greenhouse_token")
        or m.get("greenhouse_board")
        or m.get("lever_slug")
        or m.get("lever_client")
        or m.get("ashby_org")
        or m.get("ashby_board")
        or m.get("careers_url")
    )


def is_scout_target_company(company: Company) -> bool:
    """True for companies seeded from scout_targets.yaml (tier or ATS token)."""
    meta = company.metadata_json or {}
    if meta.get("tier") in _TIER_ORDER:
        return True
    return company_has_ats_metadata(meta) and not is_junk_scout_company(company)


def is_junk_scout_company(company: Company) -> bool:
    name = (company.name or "").strip().lower()
    return name in _JUNK_COMPANY_NAMES or name.startswith("acme ")


def dedupe_companies(companies: list[Company]) -> list[Company]:
    """One row per domain (prefer scout targets and richer metadata)."""
    by_domain: dict[str, Company] = {}
    no_domain: list[Company] = []
    for company in companies:
        if is_junk_scout_company(company):
            continue
        domain = (company.domain or "").strip().lower()
        if not domain:
            if is_scout_target_company(company):
                no_domain.append(company)
            continue
        existing = by_domain.get(domain)
        if existing is None or _company_rank(company) < _company_rank(existing):
            by_domain[domain] = company
    out = list(by_domain.values()) + no_domain
    out.sort(key=_company_sort_key)
    return out


def _company_rank(company: Company) -> tuple[int, int, str]:
    meta = company.metadata_json or {}
    tier = _TIER_ORDER.get(str(meta.get("tier") or "").lower(), 9)
    has_token = 0 if company_has_ats_metadata(meta) else 1
    return (tier, has_token, company.name.lower())


def _company_sort_key(company: Company) -> tuple[int, int, str]:
    meta = company.metadata_json or {}
    tier = _TIER_ORDER.get(str(meta.get("tier") or "").lower(), 9)
    last = _last_scouted_ts(company) or _last_tavily_scouted_ts(company)
    never = 0 if last is None else 1
    return (never, tier, company.name.lower())


def _last_scouted_ts(company: Company) -> float | None:
    raw = (company.metadata_json or {}).get("last_scouted_at")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def select_companies_for_ats_scout(
    companies: list[Company],
    *,
    max_per_run: int,
    min_hours_between: float,
) -> tuple[list[Company], int, bool]:
    """Pick scout-target companies for direct ATS API board scans."""
    return _select_rotated(
        dedupe_companies(companies),
        max_per_run=max_per_run,
        min_hours_between=min_hours_between,
        last_ts_fn=_last_scouted_ts,
        require_target=True,
    )


def select_companies_for_tavily_scout(
    companies: list[Company],
    *,
    max_per_run: int,
    min_hours_between: float,
) -> tuple[list[Company], int, bool]:
    """Pick scout-target companies for Tavily ATS/careers searches."""
    return _select_rotated(
        dedupe_companies(companies),
        max_per_run=max_per_run,
        min_hours_between=min_hours_between,
        last_ts_fn=_last_tavily_scouted_ts,
        require_target=True,
    )


def _select_rotated(
    companies: list[Company],
    *,
    max_per_run: int,
    min_hours_between: float,
    last_ts_fn,
    require_target: bool,
) -> tuple[list[Company], int, bool]:
    now = datetime.now(timezone.utc).timestamp()
    min_gap = min_hours_between * 3600
    eligible: list[Company] = []
    skipped = 0
    cooldown_pool: list[Company] = []
    for company in companies:
        if require_target and not is_scout_target_company(company):
            continue
        if not (company.domain or company_has_ats_metadata(company.metadata_json)):
            continue
        last = last_ts_fn(company)
        if last is not None and (now - last) < min_gap:
            skipped += 1
            cooldown_pool.append(company)
            continue
        eligible.append(company)

    eligible.sort(key=_company_sort_key)
    cap = max(1, max_per_run) if max_per_run > 0 else len(eligible)
    if eligible:
        return eligible[:cap], skipped, False

    # Every target is on cooldown — still scan the stalest boards so ATS is not a no-op.
    if cooldown_pool and max_per_run > 0:
        cooldown_pool.sort(
            key=lambda company: (
                last_ts_fn(company) or 0,
                *_company_sort_key(company),
            )
        )
        return cooldown_pool[:cap], skipped, True

    return [], skipped, False


def mark_company_scouted(company: Company) -> None:
    meta = dict(company.metadata_json or {})
    meta["last_scouted_at"] = datetime.now(timezone.utc).isoformat()
    company.metadata_json = meta


def company_eligible_for_tavily(company: Company) -> bool:
    return is_scout_target_company(company) and bool((company.name or "").strip())


def _last_tavily_scouted_ts(company: Company) -> float | None:
    raw = (company.metadata_json or {}).get("last_tavily_scouted_at")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def mark_company_tavily_scouted(company: Company) -> None:
    meta = dict(company.metadata_json or {})
    meta["last_tavily_scouted_at"] = datetime.now(timezone.utc).isoformat()
    company.metadata_json = meta
