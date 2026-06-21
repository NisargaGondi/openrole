"""Sidebar controls for CareerShift / Handshake Playwright login."""

from __future__ import annotations

import streamlit as st

from openrole.integrations.browser_login import run_careershift_login, run_handshake_login
from openrole.scrapers.careershift_client import is_ready as careershift_ready
from openrole.scrapers.handshake_client import handshake_profile_ready


def render_login_sidebar() -> None:
    with st.sidebar:
        st.divider()
        st.caption("Login opens a visible browser. Job scout / people search run headless.")
        cs_ok = careershift_ready()
        hs_ok = handshake_profile_ready()
        st.write(f"{'✓' if cs_ok else '○'} CareerShift")
        st.write(f"{'✓' if hs_ok else '○'} Handshake")

        clear = st.checkbox("Clear saved profile first", value=False, key="login_clear_profile")

        if st.button("CareerShift login", use_container_width=True, key="btn_careershift_login"):
            with st.spinner("Opening Chrome — sign in with your CMU CareerShift account…"):
                ok, msg = run_careershift_login(force=True, clear_profile=clear)
            if ok:
                st.success(msg)
            else:
                st.error(msg)

        if st.button("Handshake login", use_container_width=True, key="btn_handshake_login"):
            with st.spinner("Opening Chrome — complete CMU SSO in the browser…"):
                ok, msg = run_handshake_login(force=True, clear_profile=clear)
            if ok:
                st.success(msg)
            else:
                st.error(msg)
