"""Tests for tier-based contact quota selection."""

from openrole.agents.contact_quota import select_contacts_by_quota
from openrole.schemas.contact import ContactTier, DiscoveredContact


def _contact(name: str, tier: ContactTier, score: int, *, alum: bool = False) -> DiscoveredContact:
    return DiscoveredContact(
        full_name=name,
        title=f"{tier.name} title",
        tier=tier,
        relevance_score=score,
        is_cmu_alumni=alum,
        metadata_json={"is_cmu_alumni": alum},
    )


def test_quota_caps_engineers_and_managers():
    pool = [
        _contact(f"Eng{i}", ContactTier.TEAM_ENGINEER, 100 - i) for i in range(8)
    ] + [
        _contact(f"Exec{i}", ContactTier.EXECUTIVE, 90 - i) for i in range(5)
    ] + [
        _contact(f"Mgr{i}", ContactTier.HIRING_MANAGER, 80 - i) for i in range(5)
    ]
    selected = select_contacts_by_quota(pool)
    tiers = [c.tier for c in selected]
    assert tiers.count(ContactTier.TEAM_ENGINEER) <= 4
    assert tiers.count(ContactTier.EXECUTIVE) <= 3
    assert tiers.count(ContactTier.HIRING_MANAGER) <= 3
    assert len(selected) >= 10


def test_quota_adds_cmu_alumni():
    pool = [
        _contact("Eng1", ContactTier.TEAM_ENGINEER, 95),
        _contact("Eng2", ContactTier.TEAM_ENGINEER, 94),
        _contact("Exec1", ContactTier.EXECUTIVE, 93),
        _contact("Exec2", ContactTier.EXECUTIVE, 92),
        _contact("Exec3", ContactTier.EXECUTIVE, 91),
        _contact("Mgr1", ContactTier.HIRING_MANAGER, 90),
        _contact("Mgr2", ContactTier.HIRING_MANAGER, 89),
        _contact("Mgr3", ContactTier.HIRING_MANAGER, 88),
        _contact("Alum1", ContactTier.CMU_ALUMNI, 70, alum=True),
        _contact("Alum2", ContactTier.CMU_ALUMNI, 69, alum=True),
        _contact("Alum3", ContactTier.CMU_ALUMNI, 68, alum=True),
    ]
    selected = select_contacts_by_quota(pool)
    alumni = sum(1 for c in selected if c.is_cmu_alumni)
    assert alumni >= 3
    assert len(selected) <= 13
