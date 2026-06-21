"""Signal vertical pipeline — circular icon badges + glowing connectors."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import streamlit as st

from openrole.db.models import Contact, Job
from openrole.db.repository import list_contacts_for_job, list_outreach_drafts
from openrole.db.session import get_session_factory
from openrole.ui.signal.icons import STEP_ICONS

PIPELINE_STEPS: tuple[tuple[str, str, str], ...] = (
    ("role", "Discover", "Job & posting"),
    ("people", "People", "Find contacts"),
    ("research", "Research", "Evidence briefs"),
    ("outreach", "Outreach", "Draft emails"),
    ("apply", "Apply", "Resume & Q&A"),
)


class StepState(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    DONE = "done"


@dataclass
class StepInfo:
    key: str
    label: str
    caption: str
    state: StepState


def _infer_step_states(job: Job, active: str) -> list[StepInfo]:
    factory = get_session_factory()
    contacts: list[Contact] = []
    with factory() as session:
        if job.company_id:
            contacts = list_contacts_for_job(
                session, company_id=job.company_id, source_job_id=job.id
            )
        drafts = list_outreach_drafts(session, job_id=job.id, limit=1)
    researched = sum(1 for c in contacts if c.research_brief)
    drafted = len(drafts) > 0
    resume_done = bool((job.raw_payload or {}).get("resume_report"))

    done_keys: set[str] = {"role"}
    if contacts:
        done_keys.add("people")
    if researched:
        done_keys.add("research")
    if drafted:
        done_keys.add("outreach")
    if resume_done:
        done_keys.add("apply")

    result: list[StepInfo] = []
    for key, label, caption in PIPELINE_STEPS:
        if key == active:
            state = StepState.ACTIVE
        elif key in done_keys:
            state = StepState.DONE
        else:
            state = StepState.PENDING
        result.append(StepInfo(key=key, label=label, caption=caption, state=state))
    return result


def _rail_html(steps: list[StepInfo]) -> str:
    parts = ['<div class="or-sig-rail">']
    for i, step in enumerate(steps):
        icon = STEP_ICONS.get(step.key, "")
        parts.append(
            f'<div class="or-sig-rail-item or-sig-state-{step.state.value}">'
            f'<div class="or-sig-badge">{icon}</div>'
            f'<div class="or-sig-rail-label">{step.label}</div>'
            f'<div class="or-sig-rail-cap">{step.caption}</div>'
            f"</div>"
        )
        if i < len(steps) - 1:
            lit = step.state in (StepState.ACTIVE, StepState.DONE)
            parts.append(f'<div class="or-sig-rail-line {"or-sig-line-lit" if lit else ""}"></div>')
    parts.append("</div>")
    return "".join(parts)


def render_pipeline_rail(*, job: Job, active_step: str) -> str:
    steps = _infer_step_states(job, active_step)
    st.markdown(_rail_html(steps), unsafe_allow_html=True)

    step_keys = [s.key for s in steps]
    labels_map = {s.key: s.label for s in steps}
    idx = step_keys.index(active_step) if active_step in step_keys else 0

    picked = st.radio(
        "Pipeline step",
        options=step_keys,
        index=idx,
        format_func=lambda k: labels_map[k],
        key=f"sig_rail_{job.id}",
        label_visibility="collapsed",
    )
    if picked != active_step:
        st.session_state["workbench_step"] = picked
    return picked
