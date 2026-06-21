"""Job scout discovery and run reports."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from openrole.schemas.job import ParsedJob


class ScoutHit(BaseModel):
    """A job candidate found by the scout before persistence."""

    parsed: ParsedJob
    source: str  # jobspy_indeed, jobspy_linkedin, greenhouse_board, careers_url
    relevance_score: int = 0
    resume_match_score: int | None = None
    search_term: str | None = None
    role_families: list[str] = Field(default_factory=list)
    opt_status: str | None = None
    reject_reason: str | None = None


class ScoutRunReport(BaseModel):
    run_id: str
    started_at: datetime
    finished_at: datetime | None = None
    search_terms: list[str] = Field(default_factory=list)
    discovered: int = 0
    ingested_new: int = 0
    updated_existing: int = 0
    skipped_low_score: int = 0
    skipped_not_software: int = 0
    skipped_resume_mismatch: int = 0
    skipped_experience_mismatch: int = 0
    skipped_wrong_field: int = 0  # legacy alias in JSON exports
    skipped_opt: int = 0
    skipped_already_seen: int = 0
    companies_scouted_ats: int = 0
    companies_skipped_rotation: int = 0
    companies_scouted_tavily: int = 0
    companies_skipped_tavily_rotation: int = 0
    resume_label: str | None = None
    resume_scout_profile: dict[str, Any] | None = None
    trigger: str = "manual"
    resume_scored: int = 0
    scout_llm_enriched: int = 0
    scout_llm_batches: int = 0
    target_new_ingests: int = 0
    stopped_at_budget: bool = False
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    top_hits: list[dict[str, Any]] = Field(default_factory=list)
    notion_synced: int = 0
    sheets_synced: int = 0

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
