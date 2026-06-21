"""Persistent activity log panel — scout, ingest, pipeline."""

from __future__ import annotations

import html

import streamlit as st

from openrole.ui.activity import clear_activity_log, get_activity_log


def _colorize_line(line: str) -> str:
    escaped = html.escape(line)
    if "✗" in line or "Error" in line:
        return f'<span class="or-log-err">{escaped}</span>'
    if "✓" in line or "finished" in line.lower() or "complete" in line.lower():
        return f'<span class="or-log-ok">{escaped}</span>'
    if "!" in line or "warn" in line.lower() or "paused" in line.lower():
        return f'<span class="or-log-warn">{escaped}</span>'
    if "▸" in line or "Scout" in line or "Pipeline" in line:
        return f'<span class="or-log-stage">{escaped}</span>'
    return escaped


def render_activity_log_panel(*, expanded: bool = True, height: str = "min(72vh, 640px)") -> None:
    logs = get_activity_log()
    st.markdown(
        '<div class="or-log-header"><span class="or-log-dot"></span> Live Activity</div>',
        unsafe_allow_html=True,
    )
    if not logs:
        st.markdown(
            '<div class="or-log-empty">Runs will stream here — scout, ingest, pipeline steps.</div>',
            unsafe_allow_html=True,
        )
    else:
        body = "\n".join(_colorize_line(ln) for ln in logs[-60:])
        st.markdown(
            f'<pre class="or-activity-log" style="max-height:{height};">{body}</pre>',
            unsafe_allow_html=True,
        )
    c1, c2 = st.columns(2)
    if c1.button("Clear log", key="or_clear_log", use_container_width=True):
        clear_activity_log()
        st.rerun()
    c2.caption(f"{len(logs)} lines")
