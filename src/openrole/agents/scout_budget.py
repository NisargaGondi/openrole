"""Per-run fetch and LLM budgets derived from Results per term."""

from __future__ import annotations

import re
from dataclasses import dataclass

from openrole.schemas.job import ParsedJob


@dataclass(frozen=True)
class ScoutRunBudget:
    """Caps discovery + LLM work so a small Results-per-term setting stays fast."""

    results_per_term: int
    num_terms: int

    @classmethod
    def from_settings(cls, *, results_per_term: int, search_terms: list[str]) -> ScoutRunBudget:
        return cls(
            results_per_term=max(1, results_per_term),
            num_terms=max(1, len(search_terms)),
        )

    @property
    def target_new_ingests(self) -> int:
        """Max new jobs to save this run (Results per term × # terms)."""
        return self.results_per_term * self.num_terms

    @property
    def max_candidate_hits(self) -> int:
        """Stop collecting after this many passed-filter candidates."""
        return self.target_new_ingests * 2

    @property
    def max_llm_prepare(self) -> int:
        """Cap expensive refetch + LLM enrich calls per run."""
        return self.target_new_ingests + 2

    @property
    def max_tavily_companies(self) -> int:
        return max(2, min(12, self.results_per_term + 1))

    @property
    def max_tavily_url_hits(self) -> int:
        return self.target_new_ingests * 2

    @property
    def max_tavily_results_per_query(self) -> int:
        return max(3, min(8, self.results_per_term))

    @property
    def max_ats_companies(self) -> int:
        return max(2, min(15, self.results_per_term + 1))

    @property
    def max_jobs_per_ats_board(self) -> int:
        return max(3, self.results_per_term)

    @property
    def use_compact_tavily_queries(self) -> bool:
        """Fewer Tavily queries when the user asked for a small batch."""
        return self.results_per_term <= 10


def select_jobs_matching_terms(
    jobs: list[ParsedJob],
    search_terms: list[str],
    *,
    limit: int,
) -> list[ParsedJob]:
    """Keep the most relevant postings from a full ATS board listing."""
    if not jobs or limit <= 0:
        return []
    if len(jobs) <= limit:
        return jobs

    term_tokens: list[str] = []
    for term in search_terms:
        term_tokens.extend(w for w in re.split(r"[\s,/\-]+", term.lower()) if len(w) > 2)

    def _score(job: ParsedJob) -> int:
        title = (job.title or "").lower()
        blob = f"{title} {(job.description or '')[:400].lower()}"
        return sum(1 for tok in term_tokens if tok in blob)

    ranked = sorted(jobs, key=_score, reverse=True)
    matched = [j for j in ranked if _score(j) > 0]
    return (matched or ranked)[:limit]
