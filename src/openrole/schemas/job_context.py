"""Structured search filters extracted from a job posting."""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

_DEPT_SYNONYMS: dict[str, list[str]] = {
    "safeguard": ["safeguards", "safeguard", "ai safety", "ai safeguards", "safety"],
    "machine learning": ["machine learning", "ml", "ai", "artificial intelligence"],
    "sponsored products": ["sponsored products", "advertising", "ads"],
}


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

    def expanded_department_queries(self) -> list[str]:
        """Broader department tokens for Apollo title/keyword search."""
        out: list[str] = []
        for item in self.apollo_department_queries():
            _add_unique(out, item)
            lower = item.lower()
            for key, synonyms in _DEPT_SYNONYMS.items():
                if key in lower:
                    for syn in synonyms:
                        _add_unique(out, syn)
            for token in re.split(r"[\s,/\-]+", item):
                token = token.strip()
                if len(token) > 3 and token.lower() not in {"labs", "team", "group", "department"}:
                    _add_unique(out, token)
        return out[:10]

    def careershift_title_queries(self) -> list[str]:
        """Single-keyword CareerShift title searches (one term per query)."""
        queries: list[str] = []
        for item in self.expanded_department_queries()[:5]:
            _add_unique(queries, item)
        if self.role_family:
            _add_unique(queries, self.role_family)
        return queries[:6]

    def summary(self) -> str:
        parts = []
        if self.office_locations:
            parts.append("Locations: " + ", ".join(self.office_locations))
        if self.department_name:
            parts.append(f"Department: {self.department_name}")
        elif self.department_keywords:
            parts.append("Keywords: " + ", ".join(self.department_keywords[:4]))
        return " · ".join(parts) or "No context extracted"


def _add_unique(out: list[str], item: str) -> None:
    cleaned = item.strip()
    if cleaned and cleaned.lower() not in {x.lower() for x in out}:
        out.append(cleaned)
