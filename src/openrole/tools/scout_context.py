"""Load candidate + selected resume context for Job Scout."""

from __future__ import annotations

from typing import Any

from openrole.agents.resume_scout_profile import ScoutResumeProfile, build_scout_resume_profile
from openrole.agents.scout_filter import default_scout_search_terms
from openrole.config import Settings, get_settings
from openrole.db.repository import list_resumes
from openrole.db.session import session_scope
from openrole.tools.candidate_profile import load_candidate_profile


def list_scout_resume_options() -> list[dict[str, str]]:
    """Resume labels available for scout (DB synced from CANDIDATE_RESUME_PATHS)."""
    with session_scope() as session:
        rows = list_resumes(session)
    if rows:
        return [{"label": r.label, "path": r.file_path or "", "is_default": r.is_default} for r in rows]
    profile = load_candidate_profile(fetch_links=False)
    return [
        {"label": r.get("label") or "resume", "path": r.get("path") or "", "is_default": idx == 0}
        for idx, r in enumerate(profile.get("resumes") or [])
    ]


def _profile_sources(base: dict[str, Any]) -> list[str]:
    sources = ["resume"]
    if base.get("linkedin_summary"):
        sources.append("linkedin")
    if base.get("github_summary"):
        sources.append("github")
    if base.get("website_summary"):
        sources.append("website")
    return sources


def _supplementary_profile_text(base: dict[str, Any]) -> str:
    """GitHub / website / LinkedIn excerpts merged into scout term derivation."""
    chunks: list[str] = []
    if base.get("linkedin_summary"):
        chunks.append(f"LinkedIn:\n{base['linkedin_summary']}")
    if base.get("github_summary"):
        chunks.append(f"GitHub:\n{base['github_summary']}")
    if base.get("website_summary"):
        chunks.append(f"Website:\n{base['website_summary']}")
    return "\n\n".join(chunks)


def load_scout_context(
    *,
    resume_label: str | None = None,
    fetch_links: bool = True,
) -> dict[str, Any]:
    """Profile dict scoped to one resume + derived scout signals."""
    base = load_candidate_profile(fetch_links=fetch_links)
    options = list_scout_resume_options()
    if not options:
        base["scout_resume_profile"] = None
        base["warnings"] = list(base.get("warnings") or []) + [
            "No resumes found — set CANDIDATE_RESUME_PATHS in .env"
        ]
        return base

    chosen_label = resume_label
    if not chosen_label:
        default = next((o for o in options if o.get("is_default")), options[0])
        chosen_label = default["label"]

    text = ""
    with session_scope() as session:
        for row in list_resumes(session):
            if row.label == chosen_label:
                text = row.content_text or ""
                break

    if not text:
        for item in base.get("resumes") or []:
            if item.get("label") == chosen_label:
                text = item.get("text") or ""
                break

    if not text:
        base["warnings"] = list(base.get("warnings") or []) + [
            f"Could not read resume `{chosen_label}`"
        ]
        base["scout_resume_profile"] = None
        return base

    extra = _supplementary_profile_text(base)
    combined = f"{text}\n\n{extra}" if extra else text
    scout_profile: ScoutResumeProfile = build_scout_resume_profile(
        text=combined,
        label=chosen_label,
    )
    base["resumes"] = [{"label": chosen_label, "text": text}]
    base["scout_resume_profile"] = scout_profile
    base["selected_resume_label"] = chosen_label
    base["profile_sources"] = _profile_sources(base)
    return base


def scout_context_preview(
    *,
    resume_label: str | None = None,
    fetch_links: bool = True,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """UI/API payload: search terms + focus summary for the selected resume."""
    settings = settings or get_settings()
    ctx = load_scout_context(resume_label=resume_label, fetch_links=fetch_links)
    scout = ctx.get("scout_resume_profile")
    terms = default_scout_search_terms(ctx, settings)
    focus = ""
    if scout is not None and hasattr(scout, "focus_summary"):
        focus = scout.focus_summary
    return {
        "resume_label": ctx.get("selected_resume_label") or resume_label,
        "search_terms": terms,
        "focus_summary": focus,
        "profile_sources": ctx.get("profile_sources") or [],
        "warnings": ctx.get("warnings") or [],
        "location_default": settings.scout_search_location,
    }
