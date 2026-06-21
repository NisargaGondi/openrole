"""Scout runs."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from openrole.agents.job_scout import run_job_scout
from openrole.api.activity_store import log as act_log
from openrole.config import get_settings
from openrole.scheduler.scout_log import load_scout_runs
from openrole.tools.scout_context import list_scout_resume_options, scout_context_preview

router = APIRouter(tags=["scout"])


class ScoutRunBody(BaseModel):
    resume_label: str
    search_terms: list[str] = Field(default_factory=list)
    location: str | None = None
    results_per_term: int | None = None
    min_score: int | None = None
    sites: list[str] = Field(default_factory=lambda: ["indeed", "linkedin"])
    include_handshake: bool = True
    include_tavily: bool | None = None
    include_ats_boards: bool = True
    require_opt_mention: bool | None = None
    run_resume_analysis: bool = False
    dry_run: bool = False
    sync_notion: bool = False
    sync_sheets: bool = True


@router.get("/scout/resumes")
def scout_resumes():
    return {"resumes": list_scout_resume_options()}


@router.get("/scout/context")
def scout_context(resume_label: str | None = None):
    """Derive search terms from resume + LinkedIn/GitHub/website (when configured)."""
    return scout_context_preview(resume_label=resume_label, fetch_links=True)


@router.get("/scout/history")
def scout_history(limit: int = 10):
    return {"runs": load_scout_runs(limit=limit)}


@router.post("/scout/run")
def scout_run(body: ScoutRunBody):
    settings = get_settings()
    sites = tuple(s for s in body.sites if s in ("indeed", "linkedin")) or ("indeed", "linkedin")
    act_log(
        f"Scout signal · {len(body.search_terms)} terms · {'+'.join(sites)}",
        icon="radar",
    )
    progress: list[str] = []

    def on_progress(msg: str) -> None:
        progress.append(msg)
        if msg.startswith("[") and "]" in msg and not msg.lower().startswith("[scout]"):
            act_log(msg, icon="sparkles")
        else:
            act_log(f"[scout] {msg}", icon="radar")

    try:
        report = run_job_scout(
            resume_label=body.resume_label,
            search_terms=body.search_terms or None,
            location=body.location,
            sites=sites,
            results_per_term=body.results_per_term,
            min_score=body.min_score,
            include_handshake=body.include_handshake,
            include_tavily=body.include_tavily if body.include_tavily is not None else settings.scout_tavily_enabled,
            include_ats_boards=body.include_ats_boards,
            run_resume_analysis=body.run_resume_analysis,
            require_opt_mention=body.require_opt_mention,
            sync_notion=body.sync_notion,
            sync_sheets=body.sync_sheets,
            dry_run=body.dry_run,
            trigger="api",
            on_progress=on_progress,
        )
    except Exception as exc:
        act_log(str(exc), level="err", icon="alert")
        raise HTTPException(500, str(exc)) from exc

    model = settings.ingestion_model_name().rsplit("/", 1)[-1]
    act_log(
        f"Scout complete · +{report.ingested_new} roles · "
        f"{report.scout_llm_batches} [{model}] ingestion batch(es)",
        level="ok",
        icon="check",
    )
    return {"report": report.to_dict(), "progress": progress}
