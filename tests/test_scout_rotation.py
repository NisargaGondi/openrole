"""Tests for ATS rotation and scout memory."""

from datetime import datetime, timezone, timedelta

from openrole.agents.scout_rotation import (
    dedupe_companies,
    is_junk_scout_company,
    is_scout_target_company,
    mark_company_scouted,
    mark_company_tavily_scouted,
    select_companies_for_ats_scout,
    select_companies_for_tavily_scout,
)
from openrole.db.models import Company


def _company(
    name: str,
    *,
    domain: str | None = None,
    tier: str | None = "moderate",
    hours_ago: float | None = None,
    tavily_hours_ago: float | None = None,
) -> Company:
    meta: dict = {"greenhouse_token": name.lower().replace(" ", "")}
    if tier:
        meta["tier"] = tier
    if hours_ago is not None:
        ts = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
        meta["last_scouted_at"] = ts.isoformat()
    if tavily_hours_ago is not None:
        ts = datetime.now(timezone.utc) - timedelta(hours=tavily_hours_ago)
        meta["last_tavily_scouted_at"] = ts.isoformat()
    return Company(name=name, domain=domain or f"{name.lower()}.com", metadata_json=meta)


def test_junk_acme_excluded():
    assert is_junk_scout_company(Company(name="Acme Corp", domain="acme.com"))
    assert not is_scout_target_company(Company(name="Acme Corp", domain="acme.com"))


def test_scout_target_requires_tier_or_ats():
    assert is_scout_target_company(_company("Anthropic", tier="ambitious"))
    assert not is_scout_target_company(Company(name="Random Co", domain="random.com", metadata_json={}))


def test_dedupe_by_domain_prefers_tier():
    a = _company("Anthropic", domain="anthropic.com", tier="ambitious")
    b = Company(name="Anthropic Duplicate", domain="anthropic.com", metadata_json={})
    out = dedupe_companies([b, a])
    assert len(out) == 1
    assert out[0].name == "Anthropic"


def test_rotation_skips_recently_scouted():
    companies = [_company("A", hours_ago=1), _company("B", hours_ago=100)]
    picked, skipped, stale = select_companies_for_ats_scout(
        companies, max_per_run=10, min_hours_between=48
    )
    assert skipped == 1
    assert len(picked) == 1
    assert picked[0].name == "B"
    assert stale is False


def test_rotation_stale_fallback_when_all_on_cooldown():
    companies = [_company("A", hours_ago=1), _company("B", hours_ago=2), _company("C", hours_ago=3)]
    picked, skipped, stale = select_companies_for_ats_scout(
        companies, max_per_run=2, min_hours_between=48
    )
    assert skipped == 3
    assert stale is True
    assert len(picked) == 2
    assert picked[0].name == "C"
    assert picked[1].name == "B"


def test_tavily_rotation_uses_scout_targets_only():
    companies = [
        Company(name="Acme Corp", domain="acme.com", metadata_json={}),
        _company("Stripe", tier="moderate"),
        _company("Databricks", tier="ambitious"),
    ]
    picked, skipped, _stale = select_companies_for_tavily_scout(
        companies, max_per_run=5, min_hours_between=48
    )
    names = {c.name for c in picked}
    assert "Acme Corp" not in names
    assert "Stripe" in names or "Databricks" in names


def test_mark_company_scouted_sets_timestamp():
    c = _company("X")
    mark_company_scouted(c)
    assert c.metadata_json.get("last_scouted_at")


def test_tavily_rotation_separate_from_ats():
    meta = {
        "greenhouse_token": "y",
        "tier": "moderate",
        "last_tavily_scouted_at": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
    }
    c = Company(name="Y", domain="y.com", metadata_json=meta)
    picked, skipped, stale = select_companies_for_tavily_scout(
        [c], max_per_run=5, min_hours_between=48
    )
    assert skipped == 1
    assert stale is True
    assert len(picked) == 1

    c2 = _company("Z", tier="safe")
    picked2, _, _stale2 = select_companies_for_tavily_scout([c2], max_per_run=5, min_hours_between=48)
    assert len(picked2) == 1
    mark_company_tavily_scouted(c2)
    assert c2.metadata_json.get("last_tavily_scouted_at")
