"""Compact integration status + login — no sidebar."""

from __future__ import annotations

import streamlit as st

from openrole.integrations.browser_login import run_careershift_login, run_handshake_login
from openrole.scrapers.careershift_client import is_ready as careershift_ready
from openrole.scrapers.handshake_client import handshake_profile_ready


def render_integrations_bar(*, compact: bool = True) -> None:
    cs_ok = careershift_ready()
    hs_ok = handshake_profile_ready()
    cs_chip = "CS ✓" if cs_ok else "CS ○"
    hs_chip = "HS ✓" if hs_ok else "HS ○"
    st.markdown(
        f'<div class="or-int-bar">'
        f'<span class="or-chip {"or-chip-ok" if cs_ok else ""}">{cs_chip}</span>'
        f'<span class="or-chip {"or-chip-ok" if hs_ok else ""}">{hs_chip}</span>'
        f"</div>",
        unsafe_allow_html=True,
    )
    if compact:
        return
    with st.expander("Browser login (CareerShift / Handshake)", expanded=not (cs_ok and hs_ok)):
        clear = st.checkbox("Clear saved profile first", value=False, key="login_clear_profile")
        c1, c2 = st.columns(2)
        if c1.button("CareerShift login", use_container_width=True, key="btn_cs_login"):
            with st.spinner("Opening Chrome…"):
                ok, msg = run_careershift_login(force=True, clear_profile=clear)
            st.success(msg) if ok else st.error(msg)
        if c2.button("Handshake login", use_container_width=True, key="btn_hs_login"):
            with st.spinner("Opening Chrome…"):
                ok, msg = run_handshake_login(force=True, clear_profile=clear)
            st.success(msg) if ok else st.error(msg)
