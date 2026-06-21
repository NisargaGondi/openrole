"""Job Scout — Signal expanding network + live log."""

from __future__ import annotations

import importlib

import streamlit as st

from openrole.config import get_settings
from openrole.scheduler.scout_log import last_scout_run, load_scout_runs
from openrole.scrapers.handshake_client import handshake_ready
from openrole.sync.notion import notion_configured
from openrole.tools.scout_context import list_scout_resume_options, scout_context_preview
from openrole.ui.activity import append_log_line, log_activity
from openrole.ui.components.activity_log import render_activity_log_panel
from openrole.ui.components.integrations_bar import render_integrations_bar
from openrole.ui.components.page_header import render_page_header
from openrole.ui.components.signal_scout_graph import render_scout_signal_graph
from openrole.ui.navigation import go_to_home

render_page_header("scout")
render_integrations_bar(compact=True)

settings = get_settings()
resume_options = list_scout_resume_options()
if not resume_options:
    st.warning("Add resumes via `CANDIDATE_RESUME_PATHS` in `.env`.")
    st.stop()

main_col, log_col = st.columns([2.5, 1])
running = st.session_state.get("scout_running", False)

with main_col:
    render_scout_signal_graph(running=running)

    st.markdown('<div class="or-sig-panel">', unsafe_allow_html=True)
    labels = [o["label"] for o in resume_options]
    default_idx = next((i for i, o in enumerate(resume_options) if o.get("is_default")), 0)
    selected_resume = st.selectbox("Resume signal source", options=labels, index=default_idx)

    preview = scout_context_preview(resume_label=selected_resume, fetch_links=True)
    derived_terms = preview["search_terms"]
    if preview.get("focus_summary"):
        st.caption(preview["focus_summary"])
    sources = preview.get("profile_sources") or []
    if sources:
        st.caption(f"Signal from: {', '.join(sources)}")

    if st.session_state.get("_scout_terms_resume") != selected_resume:
        st.session_state["_scout_terms_resume"] = selected_resume
        st.session_state["scout_terms_input"] = ", ".join(derived_terms)

    c1, c2 = st.columns(2)
    with c1:
        terms_raw = st.text_input("Search terms", key="scout_terms_input")
        location = st.text_input("Location", value=settings.scout_search_location)
        min_score = st.slider("Min match score", 0, 100, settings.scout_min_relevance_score)
    with c2:
        results = st.number_input("Results / term", 5, 50, settings.scout_results_per_term)
        include_handshake = st.checkbox("Handshake", value=handshake_ready())
        require_opt = st.checkbox("Require OPT mention", value=settings.scout_require_opt_mention)
        run_resume = st.checkbox(f"Resume analysis ≥ {settings.scout_resume_analysis_threshold}", value=False)
        dry_run = st.checkbox("Dry run", value=False)

    sync_notion = st.checkbox("Sync Notion", value=notion_configured(), disabled=not notion_configured())
    sync_sheets = st.checkbox("Export CSV", value=True)

    if st.button("Run Scout", type="primary"):
        terms = [t.strip() for t in terms_raw.replace(";", ",").split(",") if t.strip()]
        log_activity(f"Scout signal · {len(terms)} terms · Indeed+LinkedIn")
        st.session_state["scout_running"] = True
        progress_lines: list[str] = []

        def _on_progress(msg: str) -> None:
            progress_lines.append(msg)
            if msg.startswith("[") and "]" in msg and not msg.lower().startswith("[scout]"):
                append_log_line(msg)
            else:
                append_log_line(f"[scout] {msg}")
            if progress_lines:
                status.update(label=progress_lines[-1][:72])

        try:
            from openrole.agents import job_scout as job_scout_module

            importlib.reload(job_scout_module)
            with st.status("Broadcasting scout signal…", expanded=True) as status:
                report = job_scout_module.run_job_scout(
                    resume_label=selected_resume,
                    search_terms=terms,
                    location=location,
                    sites=("indeed", "linkedin"),
                    min_score=min_score,
                    results_per_term=int(results),
                    include_handshake=include_handshake,
                    include_tavily=settings.scout_tavily_enabled,
                    run_resume_analysis=run_resume,
                    require_opt_mention=require_opt,
                    sync_notion=sync_notion,
                    sync_sheets=sync_sheets,
                    dry_run=dry_run,
                    trigger="manual",
                    on_progress=_on_progress,
                )
                for line in progress_lines[-10:]:
                    st.caption(line)
                status.update(label="Scout complete", state="complete")
            st.session_state["scout_running"] = False
            st.session_state["last_scout_report"] = report.to_dict()
            from openrole.config import get_settings

            model = get_settings().ingestion_model_name().rsplit("/", 1)[-1]
            log_activity(
                f"Scout complete · +{report.ingested_new} roles · "
                f"{report.scout_llm_batches} [{model}] ingestion batch(es)",
                level="ok",
            )
            st.success(
                f"Discovered {report.discovered} · ingested {report.ingested_new} · OPT skip {report.skipped_opt}"
            )
            st.rerun()
        except Exception as exc:
            st.session_state["scout_running"] = False
            log_activity(str(exc), level="err")
            st.error(str(exc))

    st.markdown("</div>", unsafe_allow_html=True)

    last = last_scout_run()
    if last:
        st.caption(f"Last run {(last.get('finished_at') or '')[:16]} · +{last.get('ingested_new', 0)}")
    with st.expander("Scout history"):
        st.dataframe(load_scout_runs(limit=6), use_container_width=True)

    if st.session_state.get("last_scout_report"):
        for hit in (st.session_state["last_scout_report"].get("top_hits") or [])[:6]:
            jid = hit.get("job_id")
            c1, c2 = st.columns([4, 1])
            c1.markdown(
                f'<div class="or-sig-node"><div class="or-sig-node-co">{hit.get("company")}</div>'
                f'<div class="or-sig-node-title">{hit.get("title")}</div>'
                f'<div class="or-sig-node-meta">score {hit.get("score")}</div></div>',
                unsafe_allow_html=True,
            )
            if jid and c2.button("Open", key=f"sc_{jid}"):
                go_to_home(job_id=jid, step="role")

with log_col:
    render_activity_log_panel()
