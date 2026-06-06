"""Structured search filters extracted from a job posting."""

from __future__ import annotations

from pydantic import BaseModel, Field


class JobSearchContext(BaseModel):
    """Location + department signals used for people discovery."""

    office_locations: list[str] = Field(default_factory=list)
    department_name: str | None = None
    department_keywords: list[str] = Field(default_factory=list)
    team_name: str | None = None
    role_family: str | None = None  # e.g. security, ml, platform

    def merge_stored(self, *, locations: list[str] | None, department: str | None) -> JobSearchContext:
        """Combine LLM extraction with structured ingestion fields."""
        locs = list(dict.fromkeys([*self.office_locations, *(locations or [])]))
        dept = self.department_name or department
        keywords = list(self.department_keywords)
        if dept and dept.lower() not in {k.lower() for k in keywords}:
            keywords.insert(0, dept)
        return JobSearchContext(
            office_locations=locs,
            department_name=dept,
            department_keywords=keywords,
            team_name=self.team_name,
            role_family=self.role_family,
        )

    def apollo_department_queries(self) -> list[str]:
        """Distinct Apollo q_keywords / title hints for department-scoped search."""
        out: list[str] = []
        for item in [self.department_name, self.team_name, *self.department_keywords]:
            if item and item.strip().lower() not in {x.lower() for x in out}:
                out.append(item.strip())
        return out[:6]

    def summary(self) -> str:
        parts = []
        if self.office_locations:
            parts.append("Locations: " + ", ".join(self.office_locations))
        if self.department_name:
            parts.append(f"Department: {self.department_name}")
        elif self.department_keywords:
            parts.append("Keywords: " + ", ".join(self.department_keywords[:4]))
        return " · ".join(parts) or "No context extracted"
