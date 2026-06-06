"""Human-in-the-loop review gates via LangGraph interrupt()."""

from __future__ import annotations

from typing import Literal

from langgraph.types import Command, interrupt

from openrole.graph.routing import pipeline_options
from openrole.graph.state import OpenRoleState


def outreach_review_node(state: OpenRoleState) -> Command[Literal["optimize_resume", "finalize"]]:
    drafts = state.get("outreach_drafts") or []
    evals = state.get("draft_evaluations") or []
    decision = interrupt(
        {
            "gate": "outreach_review",
            "job_id": state.get("job_id"),
            "draft_count": len(drafts),
            "evaluations": evals,
            "message": (
                f"Review {len(drafts)} outreach draft(s) on the Outreach tab. "
                "Continue to resume analysis or stop here."
            ),
            "actions": ["continue", "stop"],
        }
    )
    approved = True
    if isinstance(decision, dict):
        approved = bool(decision.get("approved", decision.get("continue", True)))
    elif isinstance(decision, bool):
        approved = decision

    opts = pipeline_options(state)
    if approved and opts.run_resume:
        return Command(goto="optimize_resume")
    return Command(goto="finalize")


def application_review_node(state: OpenRoleState) -> Command[Literal["prepare_application", "finalize"]]:
    report = state.get("resume_report") or {}
    score = report.get("match_score")
    opts = pipeline_options(state)
    decision = interrupt(
        {
            "gate": "application_review",
            "job_id": state.get("job_id"),
            "resume_match_score": score,
            "question_count": len(opts.application_questions),
            "message": (
                f"Resume match: {score}/100. "
                f"Draft answers for {len(opts.application_questions)} question(s)?"
            ),
            "actions": ["continue", "stop"],
        }
    )
    approved = True
    if isinstance(decision, dict):
        approved = bool(decision.get("approved", decision.get("continue", True)))
    elif isinstance(decision, bool):
        approved = decision

    if approved and opts.run_application and opts.application_questions:
        return Command(goto="prepare_application")
    return Command(goto="finalize")
