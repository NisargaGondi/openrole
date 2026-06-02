"""Structured job posting extracted from URLs or raw text."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ParsedJob(BaseModel):
    title: str
    company_name: str
    description: str | None = None
    department: str | None = None
    locations: list[str] = Field(default_factory=list)
    company_domain: str | None = None
    source_url: str | None = None
    source_platform: str | None = None
    apply_url: str | None = None
    external_id: str | None = None
    posted_at: datetime | None = None
    raw_payload: dict[str, Any] | None = None

    def to_db_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "department": self.department,
            "locations": self.locations or None,
            "description": self.description,
            "source_url": self.source_url,
            "source_platform": self.source_platform,
            "apply_url": self.apply_url or self.source_url,
            "posted_at": self.posted_at,
            "raw_payload": self.raw_payload,
        }
