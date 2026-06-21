"""Structured contact from Apollo people search."""

from __future__ import annotations

from enum import IntEnum
from typing import Any

from pydantic import BaseModel, Field


DISCOVERY_SOURCE_APOLLO = "apollo"
DISCOVERY_SOURCE_CAREERSHIFT = "careershift"
DISCOVERY_SOURCE_TAVILY = "tavily"
DISCOVERY_SOURCE_BOTH = "both"

DISCOVERY_SOURCE_LABELS: dict[str, str] = {
    DISCOVERY_SOURCE_APOLLO: "Apollo",
    DISCOVERY_SOURCE_CAREERSHIFT: "CareerShift",
    DISCOVERY_SOURCE_TAVILY: "Tavily",
    DISCOVERY_SOURCE_BOTH: "Apollo + CareerShift",
}


def compute_discovery_source(meta: dict[str, Any] | None) -> str:
    """Legacy single label — prefer discovery_source_label for display."""
    if not meta:
        return DISCOVERY_SOURCE_APOLLO
    if meta.get("tavily_search") and not meta.get("apollo_search") and not meta.get("careershift_search"):
        return DISCOVERY_SOURCE_TAVILY
    apollo = bool(meta.get("apollo_search") or meta.get("apollo_person_id"))
    careershift = bool(meta.get("careershift_search") or meta.get("careershift_contact_id"))
    if apollo and careershift:
        return DISCOVERY_SOURCE_BOTH
    if careershift:
        return DISCOVERY_SOURCE_CAREERSHIFT
    if meta.get("tavily_search"):
        return DISCOVERY_SOURCE_TAVILY
    return DISCOVERY_SOURCE_APOLLO


def discovery_source_label(meta: dict[str, Any] | None) -> str:
    """Human-readable source tags (may combine Tavily + Apollo + CareerShift)."""
    if not meta:
        return "Unknown"
    parts: list[str] = []
    if meta.get("tavily_search"):
        parts.append("Tavily")
    if meta.get("apollo_search") or meta.get("apollo_person_id"):
        parts.append("Apollo")
    if meta.get("careershift_search") or meta.get("careershift_contact_id"):
        parts.append("CareerShift")
    return " · ".join(parts) if parts else "Unknown"


__all__ = [
    "ContactTier",
    "DiscoveredContact",
    "DISCOVERY_SOURCE_APOLLO",
    "DISCOVERY_SOURCE_BOTH",
    "DISCOVERY_SOURCE_CAREERSHIFT",
    "DISCOVERY_SOURCE_TAVILY",
    "DISCOVERY_SOURCE_LABELS",
    "compute_discovery_source",
    "discovery_source_label",
]


class ContactTier(IntEnum):
    """Priority tiers for outreach (lower number = higher priority)."""

    EXECUTIVE = 1
    HIRING_MANAGER = 2
    ROLE_RECRUITER = 3
    TEAM_ENGINEER = 4
    CMU_ALUMNI = 5
    GENERAL_RECRUITER = 6
    OTHER = 7


class DiscoveredContact(BaseModel):
    full_name: str
    title: str | None = None
    email: str | None = None
    linkedin_url: str | None = None
    location: str | None = None
    apollo_person_id: str | None = None
    tier: ContactTier = ContactTier.OTHER
    priority_rank: int = 99
    priority_reason: str = ""
    relevance_score: int = 0
    is_cmu_alumni: bool = False
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    def to_db_dict(self, *, company_id: str, source_job_id: str) -> dict[str, Any]:
        meta = {
            **self.metadata_json,
            "apollo_person_id": self.apollo_person_id,
            "careershift_contact_id": self.metadata_json.get("careershift_contact_id"),
            "tier": self.tier.name,
            "source_job_id": source_job_id,
            "is_cmu_alumni": self.is_cmu_alumni,
            "relevance_score": self.relevance_score,
        }
        meta["discovery_source"] = compute_discovery_source(meta)
        return {
            "company_id": company_id,
            "full_name": self.full_name,
            "title": self.title,
            "email": self.email,
            "linkedin_url": self.linkedin_url,
            "location": self.location,
            "priority_rank": self.priority_rank,
            "priority_reason": self.priority_reason,
            "metadata_json": meta,
        }
