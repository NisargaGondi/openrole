"""OpenRole Signal theme — indigo/coral network aesthetic."""

from __future__ import annotations

import streamlit as st

from openrole.ui.components.signal_background import render_signal_background

STATUS_COLORS: dict[str, str] = {
    "discovered": "#6366f1",
    "reviewing": "#8b5cf6",
    "applied": "#f59e0b",
    "assessment": "#f97316",
    "interviewing": "#a855f7",
    "waitlist": "#64748b",
    "offer": "#22c55e",
    "rejected": "#ef4444",
    "archived": "#94a3b8",
}

KANBAN_COLUMNS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("discover", "Discover", ("discovered", "reviewing")),
    ("active", "In progress", ("applied", "assessment")),
    ("interview", "Interview", ("interviewing", "waitlist")),
    ("outcome", "Outcome", ("offer", "rejected", "archived")),
)


def inject_theme() -> None:
    render_signal_background()
    st.markdown(
        """
<style>
  section[data-testid="stSidebar"],
  [data-testid="stSidebarCollapsedControl"],
  [data-testid="stSidebarNav"] { display: none !important; }

  .stApp {
    background: linear-gradient(165deg, #f8f7ff 0%, #f5f3ff 50%, #faf5ff 100%) !important;
  }
  section.main > div { position: relative; z-index: 1; max-width: 1520px; margin: 0 auto; }
  div[data-testid="stAppViewContainer"] { background: transparent !important; }
  header[data-testid="stHeader"] {
    background: rgba(255,255,255,0.82) !important;
    backdrop-filter: blur(18px);
    border-bottom: 1px solid rgba(99,102,241,0.12);
  }
  [data-testid="stTopNavigation"] { background: transparent !important; padding: 0.35rem 0 !important; }
  [data-testid="stTopNavigation"] a {
    border-radius: 999px !important; padding: 0.5rem 1.25rem !important;
    font-weight: 650 !important; color: #64748b !important;
    transition: all 0.22s ease !important;
  }
  [data-testid="stTopNavigation"] a:hover {
    background: rgba(99,102,241,0.08) !important; color: #4338ca !important;
  }
  [data-testid="stTopNavigation"] a[aria-current="page"] {
    background: linear-gradient(135deg, rgba(99,102,241,0.18), rgba(249,115,22,0.1)) !important;
    color: #4338ca !important; box-shadow: 0 2px 12px rgba(99,102,241,0.15);
  }
  .stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #6366f1, #f97316) !important;
    border: none !important; font-weight: 650 !important;
    box-shadow: 0 4px 16px rgba(249,115,22,0.25) !important;
  }
  block-container { padding-top: 1rem !important; }

  /* Page header */
  .or-signal-header { display: flex; align-items: center; gap: 0.85rem; margin-bottom: 1rem; }
  .or-signal-icon {
    display: flex; align-items: center; justify-content: center;
    width: 48px; height: 48px; border-radius: 14px;
    background: rgba(255,255,255,0.85); border: 1px solid rgba(99,102,241,0.2);
    box-shadow: 0 4px 20px rgba(99,102,241,0.1); color: #6366f1;
  }
  .or-signal-icon svg { width: 26px; height: 26px; }
  .or-signal-title {
    font-size: 1.5rem; font-weight: 800; letter-spacing: -0.03em; color: #1e1b4b;
  }
  .or-signal-sub { font-size: 0.86rem; color: #64748b; margin-top: 0.1rem; }

  /* Glass panels */
  .or-glass, .or-sig-panel {
    background: rgba(255,255,255,0.78); backdrop-filter: blur(16px);
    border: 1px solid rgba(99,102,241,0.14); border-radius: 20px;
    padding: 1.1rem 1.25rem; box-shadow: 0 8px 40px rgba(99,102,241,0.08);
  }

  /* Signal pipeline rail */
  .or-sig-rail { display: flex; flex-direction: column; align-items: center; padding: 0.5rem 0; }
  .or-sig-rail-item { text-align: center; width: 100%; }
  .or-sig-badge {
    width: 44px; height: 44px; border-radius: 50%; margin: 0 auto;
    display: flex; align-items: center; justify-content: center;
    background: #fff; border: 2px solid #c7d2fe; color: #6366f1;
    box-shadow: 0 2px 12px rgba(99,102,241,0.1);
  }
  .or-sig-badge svg { width: 20px; height: 20px; }
  .or-sig-state-active .or-sig-badge {
    border-color: #f97316; box-shadow: 0 0 0 4px rgba(249,115,22,0.2), 0 4px 16px rgba(249,115,22,0.25);
    animation: or-sig-pulse-ring 2s ease infinite;
  }
  .or-sig-state-done .or-sig-badge { border-color: #6366f1; background: #eef2ff; }
  .or-sig-rail-label { font-size: 0.72rem; font-weight: 700; color: #1e1b4b; margin-top: 0.35rem; }
  .or-sig-rail-cap { font-size: 0.62rem; color: #94a3b8; margin-bottom: 0.15rem; }
  .or-sig-rail-line {
    width: 2px; height: 14px; background: #e2e8f0; margin: 0.1rem auto;
    border-radius: 2px;
  }
  .or-sig-line-lit {
    background: linear-gradient(180deg, #6366f1, #f97316);
    box-shadow: 0 0 8px rgba(249,115,22,0.4);
  }
  @keyframes or-sig-pulse-ring {
    0%,100% { box-shadow: 0 0 0 4px rgba(249,115,22,0.15); }
    50% { box-shadow: 0 0 0 8px rgba(249,115,22,0.08); }
  }
  div[data-testid="stRadio"] { margin-top: 0.75rem; }
  div[data-testid="stRadio"] label { font-size: 0.78rem !important; font-weight: 600 !important; }

  /* Job brief card */
  .or-sig-brief {
    background: rgba(255,255,255,0.9); border: 1px solid rgba(99,102,241,0.15);
    border-radius: 16px; padding: 0.9rem 1.1rem; margin-top: 0.5rem;
    box-shadow: 0 4px 24px rgba(99,102,241,0.06);
  }
  .or-sig-brief-top { display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.35rem; }
  .or-sig-brief-co { font-size: 0.75rem; font-weight: 700; color: #6366f1; text-transform: uppercase; letter-spacing: 0.06em; }
  .or-sig-score {
    font-size: 0.68rem; font-weight: 800; padding: 0.15rem 0.5rem; border-radius: 999px;
    background: rgba(99,102,241,0.12); color: #4338ca;
  }
  .or-sig-opt {
    font-size: 0.65rem; font-weight: 700; padding: 0.12rem 0.45rem; border-radius: 999px;
    background: rgba(249,115,22,0.12); color: #ea580c;
  }
  .or-sig-brief-title { font-size: 1.05rem; font-weight: 750; color: #1e1b4b; line-height: 1.3; }
  .or-sig-brief-meta { font-size: 0.78rem; color: #64748b; margin-top: 0.35rem; }

  /* Activity log — indigo terminal */
  .or-log-header {
    font-size: 0.7rem; font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.12em; color: #6366f1; margin-bottom: 0.5rem;
    display: flex; align-items: center; gap: 0.45rem;
  }
  .or-log-dot {
    width: 8px; height: 8px; border-radius: 50%; background: #f97316;
    box-shadow: 0 0 10px #f97316; animation: or-pulse-dot 2s ease infinite;
  }
  @keyframes or-pulse-dot { 0%,100%{opacity:1} 50%{opacity:0.4} }
  .or-activity-log, .or-pipe-log {
    font-family: "SF Mono", "Fira Code", ui-monospace, monospace;
    font-size: 0.71rem; line-height: 1.5;
    background: linear-gradient(180deg, #1e1b4b 0%, #312e81 100%);
    color: #e0e7ff; padding: 0.9rem 1rem; border-radius: 16px;
    border: 1px solid rgba(99,102,241,0.35);
    overflow-y: auto; white-space: pre-wrap;
    box-shadow: 0 8px 32px rgba(30,27,75,0.25), inset 0 1px 0 rgba(255,255,255,0.06);
  }
  .or-log-ok { color: #6ee7b7; }
  .or-log-warn { color: #fcd34d; }
  .or-log-err { color: #fca5a5; }
  .or-log-stage { color: #fdba74; }
  .or-log-empty { font-size: 0.82rem; color: #64748b; padding: 0.75rem 0; }

  /* Integration chips & tiles */
  .or-int-bar { display: flex; gap: 0.45rem; margin-bottom: 0.65rem; }
  .or-chip {
    font-size: 0.68rem; font-weight: 650; padding: 0.22rem 0.6rem;
    border-radius: 999px; background: rgba(99,102,241,0.08); color: #64748b;
    border: 1px solid rgba(99,102,241,0.12);
  }
  .or-chip-ok { background: rgba(34,197,94,0.12); color: #059669; border-color: rgba(34,197,94,0.25); }

  .or-sig-tile {
    background: rgba(255,255,255,0.85); border: 1px solid rgba(99,102,241,0.12);
    border-radius: 16px; padding: 1rem; margin-bottom: 0.65rem;
    box-shadow: 0 4px 20px rgba(99,102,241,0.06); min-height: 120px;
  }
  .or-sig-tile-ok { border-color: rgba(34,197,94,0.25); }
  .or-sig-tile-icon { color: #6366f1; margin-bottom: 0.4rem; }
  .or-sig-tile-icon svg { width: 28px; height: 28px; }
  .or-sig-tile-name { font-weight: 700; font-size: 0.9rem; color: #1e1b4b; }
  .or-sig-tile-status { font-size: 0.78rem; color: #059669; margin: 0.25rem 0; }
  .or-sig-tile-off .or-sig-tile-status { color: #94a3b8; }
  .or-sig-tile-hint { font-size: 0.65rem; color: #94a3b8; word-break: break-all; }

  /* Library job nodes */
  .or-sig-node {
    background: rgba(255,255,255,0.88); border: 1px solid rgba(99,102,241,0.14);
    border-radius: 16px; padding: 0.85rem 1rem; margin-bottom: 0.5rem;
    box-shadow: 0 4px 16px rgba(99,102,241,0.06);
    border-left: 3px solid #6366f1;
  }
  .or-sig-node-title { font-weight: 700; color: #1e1b4b; font-size: 0.92rem; }
  .or-sig-node-co { color: #6366f1; font-size: 0.78rem; font-weight: 600; }
  .or-sig-node-meta { font-size: 0.72rem; color: #64748b; margin-top: 0.3rem; }

  .or-kpi {
    background: rgba(255,255,255,0.8); border-radius: 14px; padding: 0.85rem 1rem;
    border: 1px solid rgba(99,102,241,0.1);
  }
  .or-kpi-label { font-size: 0.65rem; text-transform: uppercase; letter-spacing: 0.07em; color: #6366f1; font-weight: 700; }
  .or-kpi-value { font-size: 1.5rem; font-weight: 800; color: #1e1b4b; }
  .or-kpi-sub { font-size: 0.72rem; color: #64748b; }

  div[data-testid="stExpander"] {
    background: rgba(255,255,255,0.85) !important;
    border: 1px solid rgba(99,102,241,0.1) !important;
    border-radius: 16px !important;
  }
  .or-delete-btn button {
    background: rgba(239,68,68,0.08) !important; color: #dc2626 !important;
    border: 1px solid rgba(239,68,68,0.3) !important;
  }
  .or-job-description { font-size: 0.94rem; line-height: 1.6; color: #334155; }
  .or-status-dot { display: inline-block; width: 0.45rem; height: 0.45rem; border-radius: 50%; margin-right: 0.3rem; }
</style>
""",
        unsafe_allow_html=True,
    )


def kpi_tile(label: str, value: str | int, sub: str = "") -> str:
    sub_html = f'<div class="or-kpi-sub">{sub}</div>' if sub else ""
    return (
        f'<div class="or-kpi"><div class="or-kpi-label">{label}</div>'
        f'<div class="or-kpi-value">{value}</div>{sub_html}</div>'
    )


def job_card_html(*, title: str, company: str, score: int | None, source: str | None, status: str) -> str:
    color = STATUS_COLORS.get(status, "#6366f1")
    score_html = f'<span class="or-sig-score">{score}</span>' if score is not None else ""
    return (
        f'<div class="or-sig-node" style="border-left-color:{color};">'
        f'<div class="or-sig-node-co">{company}</div>'
        f'<div class="or-sig-node-title">{title}</div>'
        f'<div class="or-sig-node-meta">{status} {score_html}</div></div>'
    )
