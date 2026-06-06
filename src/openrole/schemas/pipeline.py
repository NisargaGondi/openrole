"""Pipeline run configuration for LangGraph orchestration."""

from __future__ import annotations

from pydantic import BaseModel, Field


class PipelineOptions(BaseModel):
    """Which stages to run in a full job pipeline."""

    run_people: bool = True
    run_research: bool = True
    run_outreach: bool = True
    run_resume: bool = True
    run_application: bool = False

    research_limit: int = Field(default=5, ge=1, le=15)
    max_draft_iterations: int = Field(default=3, ge=1, le=5)
    resume_label: str | None = None
    application_questions: list[str] = Field(default_factory=list)

    @classmethod
    def people_only(cls) -> PipelineOptions:
        return cls(
            run_people=True,
            run_research=False,
            run_outreach=False,
            run_resume=False,
            run_application=False,
        )

    @classmethod
    def outreach_prep(cls, *, limit: int = 5) -> PipelineOptions:
        return cls(
            run_people=True,
            run_research=True,
            run_outreach=True,
            run_resume=False,
            run_application=False,
            research_limit=limit,
        )

    @classmethod
    def full_apply(
        cls,
        *,
        questions: list[str] | None = None,
        resume_label: str | None = None,
        limit: int = 5,
    ) -> PipelineOptions:
        return cls(
            run_people=True,
            run_research=True,
            run_outreach=True,
            run_resume=True,
            run_application=bool(questions),
            application_questions=list(questions or []),
            resume_label=resume_label,
            research_limit=limit,
        )

    def to_state_dict(self) -> dict:
        return self.model_dump()

    @classmethod
    def from_state(cls, raw: dict | None) -> PipelineOptions:
        if not raw:
            return cls()
        return cls.model_validate(raw)
