"""Integration status tiles — Settings grid."""

from __future__ import annotations

import streamlit as st

from openrole.ui.signal.icons import INTEGRATION_ICONS


def render_integration_tiles(rows: list[tuple[str, str, bool, str]]) -> None:
    """rows: (key, name, ok, env_hint)"""
    cols = st.columns(3)
    for i, (key, name, ok, hint) in enumerate(rows):
        icon = INTEGRATION_ICONS.get(key, INTEGRATION_ICONS.get("vertex", ""))
        status = "Connected" if ok else "Not configured"
        cls = "or-sig-tile-ok" if ok else "or-sig-tile-off"
        with cols[i % 3]:
            st.markdown(
                f'<div class="or-sig-tile {cls}">'
                f'<div class="or-sig-tile-icon">{icon}</div>'
                f'<div class="or-sig-tile-name">{name}</div>'
                f'<div class="or-sig-tile-status">{"✓ " if ok else "○ "}{status}</div>'
                f'<div class="or-sig-tile-hint">{hint}</div>'
                f"</div>",
                unsafe_allow_html=True,
            )
