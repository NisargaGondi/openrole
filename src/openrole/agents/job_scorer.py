"""Resume-aware relevance scoring for scout hits (fast heuristic + optional LLM)."""

from __future__ import annotations

import re
from typing import Any

from openrole.schemas.job import ParsedJob

# Skills/role signals fallback when no resume is loaded
_DEFAULT_POSITIVE = frozenset(
    {
        "machine learning",
        "ml",
        "deep learning",
        "pytorch",
        "tensorflow",
        "llm",
        "nlp",
        "computer vision",
        "security",
        "ai",
        "artificial intelligence",
        "software engineer",
        "research engineer",
        "applied scientist",
        "kubernetes",
        "python",
        "distributed",
        "inference",
        "training",
    }
)


def _tokenize(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9+#.]{2,}", text.lower())
    return set(words)


def _bigrams(text: str) -> set[str]:
    words = re.findall(r"[a-z]{3,}", text.lower())
    return {f"{words[i]} {words[i+1]}" for i in range(len(words) - 1)}


def build_resume_corpus(profile: dict[str, Any]) -> str:
    parts: list[str] = []
    scout = profile.get("scout_resume_profile")
    if scout is not None and hasattr(scout, "focus_summary"):
        parts.append(scout.focus_summary)
    if profile.get("role_search"):
        parts.append(str(profile["role_search"]))
    for r in profile.get("resumes") or []:
        if r.get("text"):
            parts.append(r["text"][:8000])
    if profile.get("github_summary"):
        parts.append(str(profile["github_summary"])[:2000])
    if profile.get("linkedin_summary"):
        parts.append(str(profile["linkedin_summary"])[:2000])
    if profile.get("website_summary"):
        parts.append(str(profile["website_summary"])[:2000])
    if profile.get("prompt_context"):
        parts.append(str(profile["prompt_context"])[:4000])
    return "\n".join(parts)


def _resume_keyword_set(profile: dict[str, Any]) -> set[str]:
    scout = profile.get("scout_resume_profile")
    if scout is not None and hasattr(scout, "skills"):
        return set(scout.skills) | set(scout.phrases)
    return _tokenize(build_resume_corpus(profile).lower())


def score_job_relevance(
    parsed: ParsedJob,
    *,
    profile: dict[str, Any],
    search_term: str | None = None,
) -> int:
    """0–100 relevance vs candidate resumes and role search (no LLM)."""
    job_text = " ".join(
        filter(
            None,
            [parsed.title, parsed.department, parsed.description, " ".join(parsed.locations or [])],
        )
    ).lower()
    if not job_text.strip():
        return 0

    corpus = build_resume_corpus(profile).lower()
    resume_tokens = _tokenize(corpus)
    job_tokens = _tokenize(job_text)
    job_bigrams = _bigrams(job_text)

    if not resume_tokens:
        resume_tokens = _tokenize(search_term or profile.get("role_search") or "") | _DEFAULT_POSITIVE

    overlap = resume_tokens & job_tokens
    score = min(40, len(overlap) * 4)

    # Title alignment
    title_l = (parsed.title or "").lower()
    role_search = (profile.get("role_search") or search_term or "").lower()
    for term in re.split(r"[,;/|]+", role_search):
        t = term.strip()
        if len(t) > 3 and t in title_l:
            score += 15
            break

    # Domain keyword hits from resume-derived vocabulary (not a fixed field list)
    positive = _resume_keyword_set(profile)
    domain_hits = sum(1 for kw in positive if len(kw) > 2 and kw in job_text)
    score += min(25, domain_hits * 3)

    # Bigram overlap (e.g. "machine learning")
    resume_bigrams = _bigrams(corpus)
    score += min(15, len(resume_bigrams & job_bigrams) * 5)

    # Penalize very short descriptions (likely incomplete scrape)
    if parsed.description and len(parsed.description) < 200:
        score -= 10

    return max(0, min(100, score))


def should_run_resume_analysis(relevance_score: int, *, threshold: int) -> bool:
    return relevance_score >= threshold
