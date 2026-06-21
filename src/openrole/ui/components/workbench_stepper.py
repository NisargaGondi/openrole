"""Horizontal stepper for the Role Workbench."""

from __future__ import annotations

import streamlit as st

WORKBENCH_STEPS: tuple[tuple[str, str, str], ...] = (
    ("role", "Role", "Pick the job you're working on"),
    ("people", "People", "Discover & rank contacts"),
    ("research", "Research", "Briefs before outreach"),
    ("outreach", "Outreach", "Email & LinkedIn drafts"),
    ("apply", "Apply", "Resume ATS & application Q&A"),
)


def _step_index(step_id: str) -> int:
    for i, (sid, _, _) in enumerate(WORKBENCH_STEPS):
        if sid == step_id:
            return i
    return 0


def render_workbench_stepper(*, job_id: str, active_step: str) -> str:
    """Render clickable stepper; returns selected step id."""
    key = f"workbench_step_{job_id[:8]}"
    active_idx = _step_index(active_step)

    st.markdown('<div class="or-stepper-wrap">', unsafe_allow_html=True)
    cols = st.columns(len(WORKBENCH_STEPS))
    selected = active_step

    for col, (step_id, label, hint) in zip(cols, WORKBENCH_STEPS, strict=True):
        idx = _step_index(step_id)
        state = "done" if idx < active_idx else ("active" if idx == active_idx else "")
        with col:
            if st.button(
                f"{idx + 1}. {label}",
                key=f"{key}_{step_id}",
                use_container_width=True,
                type="primary" if step_id == active_step else "secondary",
                help=hint,
            ):
                selected = step_id
                st.session_state["workbench_step"] = step_id

    st.markdown("</div>", unsafe_allow_html=True)

    if selected != active_step:
        st.session_state["workbench_step"] = selected
    return st.session_state.get("workbench_step", active_step)


def step_progress_label(step_id: str) -> str:
    for sid, label, hint in WORKBENCH_STEPS:
        if sid == step_id:
            return f"**{label}** — {hint}"
    return ""
