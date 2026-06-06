"""Structured person research and outreach draft schemas."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class PersonResearchBrief(BaseModel):
    contact_id: str | None = None
    full_name: str
    title: str | None = None
    company_name: str
    talking_points: list[str] = Field(default_factory=list)
    suggested_hook: str = ""
    tone_notes: str = ""
    gaps: list[str] = Field(default_factory=list)
    confidence: float = 0.5
    layers_used: list[str] = Field(default_factory=list)
    sources: list[dict[str, Any]] = Field(default_factory=list)
    apollo_snapshot: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_db_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class OutreachDraft(BaseModel):
    contact_id: str
    job_id: str | None = None
    channel: str  # email | linkedin
    subject: str | None = None
    body: str
    status: str = "draft"

    def to_db_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
