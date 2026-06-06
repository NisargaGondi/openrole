"""Application question answer drafts."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class ApplicationAnswer(BaseModel):
    question: str
    answer: str
    notes: str | None = None


class ApplicationDraft(BaseModel):
    job_id: str
    resume_label: str | None = None
    answers: list[ApplicationAnswer] = Field(default_factory=list)
    tone_notes: str = ""
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_db_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    def to_answers_json(self) -> dict[str, Any]:
        return {
            "resume_label": self.resume_label,
            "tone_notes": self.tone_notes,
            "created_at": self.created_at,
            "answers": [a.model_dump() for a in self.answers],
        }
