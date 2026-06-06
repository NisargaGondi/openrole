"""Structured resume vs JD analysis output."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class ResumeEditSuggestion(BaseModel):
    section: str = ""
    issue: str = ""
    suggestion: str = ""


class ResumeOptimizationReport(BaseModel):
    job_id: str
    resume_label: str
    resume_path: str | None = None
    match_score: int = Field(ge=0, le=100, description="0-100 fit vs JD")
    summary: str = ""
    strengths: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    missing_keywords: list[str] = Field(default_factory=list)
    ats_risks: list[str] = Field(default_factory=list)
    suggested_edits: list[ResumeEditSuggestion] = Field(default_factory=list)
    recommended_resume: str | None = None
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_db_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
