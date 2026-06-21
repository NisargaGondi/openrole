"""OpenRole — top navigation entry (Signal theme)."""

import streamlit as st

from openrole.db.session import init_db
from openrole.ui.navigation import (
    PAGE_HOME,
    PAGE_JOB_LIBRARY,
    PAGE_SCOUT,
    PAGE_SETTINGS,
)
from openrole.ui.theme import inject_theme

st.set_page_config(
    page_title="OpenRole",
    page_icon="◉",
    layout="wide",
    initial_sidebar_state="collapsed",
)


@st.cache_resource
def _ensure_db() -> bool:
    init_db()
    return True


_ensure_db()
inject_theme()

home = st.Page(PAGE_HOME, title="Home", icon="🏠", default=True)
scout = st.Page(PAGE_SCOUT, title="Scout", icon="📡")
library = st.Page(PAGE_JOB_LIBRARY, title="Library", icon="📚")
settings = st.Page(PAGE_SETTINGS, title="Settings", icon="⚙️")

pg = st.navigation([home, scout, library, settings], position="top")
pg.run()
