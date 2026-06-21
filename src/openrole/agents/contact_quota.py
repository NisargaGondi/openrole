"""Select people contacts by tier quotas for outreach diversity."""

from __future__ import annotations

from openrole.agents.outreach_prompts import infer_tier_from_title
from openrole.schemas.contact import ContactTier, DiscoveredContact

# Max per tier before CMU backfill / minimum total backfill.
TIER_QUOTAS: dict[ContactTier, int] = {
    ContactTier.TEAM_ENGINEER: 4,
    ContactTier.EXECUTIVE: 3,
    ContactTier.HIRING_MANAGER: 3,
}

CMU_ALUMNI_TARGET = 3
MIN_CONTACTS = 10
MAX_CONTACTS = 13

_PRIMARY_TIERS = (
    ContactTier.EXECUTIVE,
    ContactTier.HIRING_MANAGER,
    ContactTier.TEAM_ENGINEER,
)


def normalize_contact_tiers(contacts: list[DiscoveredContact]) -> list[DiscoveredContact]:
    """Re-classify OTHER contacts when title clearly maps to engineer/manager/exec."""
    for contact in contacts:
        if contact.tier != ContactTier.OTHER or not contact.title:
            continue
        inferred = infer_tier_from_title(contact.title)
        if inferred != ContactTier.OTHER:
            contact.tier = inferred
    return contacts


def tier_quota_counts(contacts: list[DiscoveredContact]) -> dict[str, int]:
    counts = {tier.name: 0 for tier in TIER_QUOTAS}
    counts["CMU_ALUMNI"] = 0
    for contact in contacts:
        if contact.tier in TIER_QUOTAS:
            counts[contact.tier.name] += 1
        if contact.is_cmu_alumni or (contact.metadata_json or {}).get("is_cmu_alumni"):
            counts["CMU_ALUMNI"] += 1
    return counts


def select_contacts_by_quota(
    contacts: list[DiscoveredContact],
    *,
    min_total: int = MIN_CONTACTS,
    max_total: int = MAX_CONTACTS,
) -> list[DiscoveredContact]:
    """Build a balanced outreach list: engineers, leaders, managers, CMU alumni."""
    if not contacts:
        return []

    pool = sorted(contacts, key=lambda c: c.relevance_score, reverse=True)
    pool = normalize_contact_tiers(pool)
    selected: list[DiscoveredContact] = []
    used_ids: set[int] = set()

    def _take(tier: ContactTier, limit: int) -> None:
        nonlocal selected
        if limit <= 0:
            return
        count = 0
        for contact in pool:
            if id(contact) in used_ids:
                continue
            if contact.tier != tier:
                continue
            selected.append(contact)
            used_ids.add(id(contact))
            count += 1
            if count >= limit:
                break

    for tier in _PRIMARY_TIERS:
        _take(tier, TIER_QUOTAS.get(tier, 0))

    alumni_count = sum(1 for c in selected if c.is_cmu_alumni or (c.metadata_json or {}).get("is_cmu_alumni"))
    if alumni_count < CMU_ALUMNI_TARGET:
        for contact in pool:
            if id(contact) in used_ids:
                continue
            is_alum = contact.is_cmu_alumni or (contact.metadata_json or {}).get("is_cmu_alumni")
            if not is_alum and contact.tier != ContactTier.CMU_ALUMNI:
                continue
            selected.append(contact)
            used_ids.add(id(contact))
            alumni_count += 1
            if alumni_count >= CMU_ALUMNI_TARGET:
                break

    if len(selected) < min_total:
        for contact in pool:
            if id(contact) in used_ids:
                continue
            selected.append(contact)
            used_ids.add(id(contact))
            if len(selected) >= min_total:
                break

    selected.sort(key=lambda c: c.relevance_score, reverse=True)
    return selected[:max_total]
