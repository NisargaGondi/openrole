"""Consistent Signal page headers with SVG icons."""

from __future__ import annotations

import streamlit as st

from openrole.ui.signal.icons import ICON_NETWORK, PAGE_ICONS


def render_page_header(page: str, *, subtitle: str = "") -> None:
    icon = PAGE_ICONS.get(page, ICON_NETWORK)
    title = page.capitalize() if page != "home" else "OpenRole"
    sub = subtitle or {
        "home": "Signal network · scout → people → outreach → apply",
        "scout": "Expand signals · Indeed · LinkedIn · Tavily · ATS",
        "library": "Saved role nodes · search · ingest",
        "settings": "Integration hub · diagnostics · login",
    }.get(page, "")
    st.markdown(
        f'<div class="or-signal-header">'
        f'<span class="or-signal-icon">{icon}</span>'
        f'<div><div class="or-signal-title">{title}</div>'
        f'<div class="or-signal-sub">{sub}</div></div></div>',
        unsafe_allow_html=True,
    )
