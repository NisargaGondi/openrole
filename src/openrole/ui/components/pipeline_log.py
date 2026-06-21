"""Pipeline run log panel for Streamlit."""

from __future__ import annotations

import html

import streamlit as st


def render_pipeline_log(lines: list[str]) -> None:
    if not lines:
        return
    st.markdown("**Run log**")
    body = html.escape("\n".join(lines[-50:]))
    st.markdown(
        f'<pre style="font-size:0.78rem;line-height:1.35;max-height:320px;'
        f'overflow-y:auto;background:#0e1117;color:#eaeaea;padding:0.75rem;'
        f'border-radius:6px;border:1px solid #30363d;">{body}</pre>',
        unsafe_allow_html=True,
    )


def init_log_session(key: str = "pipeline_run_log") -> list[str]:
    if key not in st.session_state:
        st.session_state[key] = []
    return st.session_state[key]
