"""Jobs list and ingestion."""

import streamlit as st
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from openrole.agents.email_writer import EmailWriterError, draft_outreach_for_contact
from openrole.agents.job_ingestion import JobIngestionError, ingest_job
from openrole.agents.people_discovery import PeopleDiscoveryError
from openrole.agents.person_research import PersonResearchError, research_contact_for_job
from openrole.agents.resume_optimizer import ResumeOptimizerError, optimize_resume_for_job
from openrole.db.models import Contact, Job
from openrole.db.repository import list_contacts_for_job, update_company_domain
from openrole.db.session import get_session_factory
from openrole.graph.main_graph import discover_and_prepare_outreach_via_graph, discover_people_via_graph, run_pipeline
from openrole.schemas.contact import DISCOVERY_SOURCE_LABELS, compute_discovery_source
from openrole.tools import apollo_client, jobspy_client


def _show_discovery_result(result: dict) -> None:
    if result.get("errors"):
        st.error("\n".join(result["errors"]))
    if result.get("search_context"):
        ctx = result["search_context"]
        st.info(
            f"**Filters:** {ctx.get('department_name') or '—'} · "
            f"Locations: {', '.join(ctx.get('office_locations') or []) or '—'}"
        )
    if result.get("contact_count"):
        st.success(f"Saved {result['contact_count']} validated contacts (max 15)")
    elif result.get("contacts"):
        st.success(f"Found {len(result['contacts'])} validated contacts")
    for w in result.get("warnings") or []:
        st.warning(w)
    val = result.get("validation_result") or {}
    if val.get("rejected_count"):
        st.caption(
            f"Filtered out {val['rejected_count']} contacts (wrong city/department)."
        )


st.header("Jobs")

tab_ingest, tab_list = st.tabs(["Ingest", "Saved jobs"])

with tab_ingest:
    st.subheader("Add a job")
    if not jobspy_client.is_available():
        st.warning(
            "JobSpy is not installed — LinkedIn/Indeed URLs need pasted text, or run "
            "`bash scripts/install_jobspy.sh` (not `pip install jobspy`)."
        )
    job_url = st.text_input("Job URL", placeholder="Greenhouse, Lever, Ashby, LinkedIn, Indeed…")
    job_text = st.text_area(
        "Pasted description (fallback for LinkedIn; optional for Workday errors)",
        height=160,
    )
    col1, col2 = st.columns(2)
    with col1:
        run_direct = st.button("Ingest & save", type="primary")
    with col2:
        run_graph = st.button("Run via LangGraph")

    if run_direct:
        try:
            with st.spinner("Fetching and parsing… (LinkedIn/Handshake can take up to a minute)"):
                result = ingest_job(
                    job_url=job_url.strip() or None,
                    job_text=job_text.strip() or None,
                )
            st.success(f"Saved job `{result['job_id']}`")
            if result.get("warnings"):
                for w in result["warnings"]:
                    st.warning(w)
            st.json(result["parsed_job"])
        except JobIngestionError as exc:
            st.error(str(exc))
        except Exception as exc:
            st.error(f"Unexpected error: {exc}")

    if run_graph:
        try:
            with st.spinner("Running pipeline…"):
                state = run_pipeline(
                    job_url=job_url.strip() or None,
                    job_text=job_text.strip() or None,
                )
            if state.get("errors"):
                st.error("\n".join(state["errors"]))
            else:
                st.success(f"Saved job `{state.get('job_id')}`")
                for w in state.get("warnings") or []:
                    st.warning(w)
                st.json(state.get("parsed_job"))
        except Exception as exc:
            st.error(str(exc))

with tab_list:
    factory = get_session_factory()
    with factory() as session:
        jobs = list(
            session.scalars(
                select(Job)
                .options(joinedload(Job.company))
                .order_by(Job.created_at.desc())
                .limit(50)
            ).unique()
        )

    if not jobs:
        st.write("No jobs yet. Use the Ingest tab to add one.")
    else:
        for job in jobs:
            company_name = job.company.name if job.company else "—"
            label = f"{job.title} @ {company_name} ({job.status.value})"
            with st.expander(label):
                st.write(f"**Platform:** {job.source_platform or '—'}")
                st.write(f"**Department:** {job.department or '—'}")
                st.write(f"**Locations:** {', '.join(job.locations or []) or '—'}")
                if job.source_url:
                    st.link_button("Posting", job.source_url)
                if job.description:
                    st.text(job.description[:2000] + ("…" if len(job.description) > 2000 else ""))

                st.divider()
                st.subheader("People")
                domain = job.company.domain if job.company else None
                dr = (job.raw_payload or {}).get("domain_resolution") if job.raw_payload else None
                if dr:
                    st.caption(
                        f"Domain `{domain or '—'}` — resolved via {dr.get('source')} "
                        f"({dr.get('confidence')})"
                    )
                else:
                    st.caption(f"Company domain: `{domain or '—'}`")

                if job.company:
                    with st.form(key=f"domain_form_{job.id}"):
                        new_domain = st.text_input(
                            "Company email domain",
                            value=domain or "",
                            placeholder="crowdstrike.com",
                        )
                        if st.form_submit_button("Save domain"):
                            try:
                                with factory() as session:
                                    update_company_domain(session, job.company.id, new_domain.strip())
                                    session.commit()
                                st.success(f"Saved domain `{new_domain.strip()}`")
                                st.rerun()
                            except Exception as exc:
                                st.error(str(exc))

                if not apollo_client.is_configured() and not domain:
                    st.warning(
                        "Set `APOLLO_API_KEY` and/or company domain to discover contacts."
                    )
                elif not domain:
                    st.warning("No company domain — set domain above or re-ingest.")
                else:
                    col_a, col_b = st.columns(2)
                    if col_a.button("Find people", key=f"people_{job.id}"):
                        try:
                            with st.spinner("Extracting context → Apollo/CareerShift → validate…"):
                                result = discover_people_via_graph(job.id)
                            _show_discovery_result(result)
                        except PeopleDiscoveryError as exc:
                            st.error(str(exc))
                        except Exception as exc:
                            st.error(f"People discovery failed: {type(exc).__name__}: {exc}")

                    if col_b.button("Find people + draft outreach", key=f"full_{job.id}"):
                        try:
                            with st.spinner("Discovery → research → drafts…"):
                                result = discover_and_prepare_outreach_via_graph(job.id)
                            _show_discovery_result(result)
                            if result.get("interrupted") or result.get("__interrupt__"):
        st.info("Pipeline paused — open **Pipeline** tab to continue after reviewing drafts.")
                            if result.get("outreach_drafts"):
                                st.success(f"Created {len(result['outreach_drafts'])} draft(s) — see Outreach tab")
                            if result.get("interrupted") or result.get("__interrupt__"):
                                st.info("Paused for review — continue on **Pipeline** tab.")
                                st.session_state["pipeline_thread_id"] = result.get("thread_id")
                        except Exception as exc:
                            st.error(f"Pipeline failed: {type(exc).__name__}: {exc}")

                show_all = st.checkbox(
                    "Show all company contacts",
                    value=False,
                    key=f"all_co_{job.id}",
                )
                with factory() as session:
                    contacts = list_contacts_for_job(
                        session,
                        company_id=job.company_id,
                        source_job_id=job.id,
                        include_all_company=show_all,
                    )

                if contacts:
                    for idx, c in enumerate(contacts):
                        tier = (c.metadata_json or {}).get("tier", "—")
                        source_tag = DISCOVERY_SOURCE_LABELS.get(
                            compute_discovery_source(c.metadata_json), "Unknown"
                        )
                        line = f"**#{c.priority_rank}** {c.full_name}"
                        if c.title:
                            line += f" — _{c.title}_"
                        st.markdown(line)
                        st.caption(f"**Source:** {source_tag} · {tier} · {c.priority_reason or '—'}")
                        if (c.metadata_json or {}).get("stale_for_job"):
                            st.caption("_Previous run — hidden unless showing all_")
                        loc = c.location or "—"
                        st.caption(f"📍 {loc}")
                        cols = st.columns(4)
                        if c.email:
                            cols[0].write(f"✉️ {c.email}")
                        elif (c.metadata_json or {}).get("stored_email_raw"):
                            cols[0].caption(
                                f"No company email (found {(c.metadata_json or {}).get('stored_email_raw')})"
                            )
                        else:
                            cols[0].caption("No email — try LinkedIn")
                        if c.linkedin_url:
                            cols[1].link_button(
                                "LinkedIn",
                                c.linkedin_url,
                                key=f"li_{job.id}_{c.id}_{idx}",
                            )
                        if cols[2].button("Research", key=f"res_{job.id}_{c.id}"):
                            try:
                                research_contact_for_job(contact_id=c.id, job_id=job.id)
                                st.success("Research brief saved")
                            except PersonResearchError as exc:
                                st.error(str(exc))
                        if cols[3].button("Draft", key=f"drf_{job.id}_{c.id}"):
                            try:
                                out = draft_outreach_for_contact(contact_id=c.id, job_id=job.id)
                                st.success("Draft saved — Outreach tab")
                                for w in out.get("profile_warnings") or []:
                                    st.warning(w)
                            except EmailWriterError as exc:
                                st.error(str(exc))
                        if c.research_brief:
                            hook = c.research_brief.get("suggested_hook", "")
                            if hook:
                                st.caption(f"Research hook: {hook[:120]}")
                elif domain or apollo_client.is_configured():
                    st.write("No contacts yet — click **Find people**.")

                st.divider()
                st.subheader("Apply")
                st.caption("Resume fit and application answers — full UI on **Apply** page.")
                if st.button("Quick resume check", key=f"resume_{job.id}"):
                    try:
                        with st.spinner("Analyzing resume vs JD…"):
                            out = optimize_resume_for_job(job_id=job.id)
                        r = out["report"]
                        st.success(f"Match score: {r.get('match_score')}/100 — see **Apply** tab for details")
                        if r.get("summary"):
                            st.write(r["summary"][:500])
                    except ResumeOptimizerError as exc:
                        st.error(str(exc))
