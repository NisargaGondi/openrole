"""Structured person research and outreach draft schemas."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


PublicSignalType = Literal[
    "linkedin_post",
    "blog",
    "talk",
    "paper",
    "github",
    "news",
    "other",
]


class PublicSignal(BaseModel):
    type: PublicSignalType = "other"
    summary: str = ""
    url: str | None = None


class PersonResearchBrief(BaseModel):
    contact_id: str | None = None
    full_name: str
    title: str | None = None
    company_name: str
    summary: str = ""
    recent_work: str = ""
    public_signals: list[PublicSignal] = Field(default_factory=list)
    outreach_angles: list[str] = Field(default_factory=list)
    talking_points: list[str] = Field(default_factory=list)
    suggested_hook: str = ""
    tone_notes: str = ""
    gaps: list[str] = Field(default_factory=list)
    confidence: float = 0.5
    layers_used: list[str] = Field(default_factory=list)
    sources: list[dict[str, Any]] = Field(default_factory=list)
    apollo_snapshot: dict[str, Any] = Field(default_factory=dict)
    tavily_queries: list[str] = Field(default_factory=list)
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_db_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
