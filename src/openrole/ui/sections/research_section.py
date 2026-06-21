"""Research briefs for workbench step 3."""

from __future__ import annotations

import streamlit as st

from openrole.agents.person_research import PersonResearchError, research_contact_for_job
from openrole.db.models import Contact, Job
from openrole.db.repository import list_contacts_for_job
from openrole.db.session import get_session_factory
from openrole.graph.pipeline_runner import stream_pipeline_updates
from openrole.schemas.pipeline import PipelineOptions


def render_research_section(job_id: str) -> None:
    st.subheader("Contact research")
    st.caption("Tavily + Apollo evidence → LLM brief for outreach personalization.")

    factory = get_session_factory()
    with factory() as session:
        job = session.get(Job, job_id)
        contacts = (
            list_contacts_for_job(session, company_id=job.company_id, source_job_id=job_id)
            if job and job.company_id
            else []
        )

    if not contacts:
        st.info("Run **People** step first to discover contacts.")
        return

    researched = [c for c in contacts if c.research_brief]
    missing = [c for c in contacts if not c.research_brief]

    c1, c2, c3 = st.columns(3)
    c1.metric("Contacts", len(contacts))
    c2.metric("Researched", len(researched))
    c3.metric("Pending", len(missing))

    if missing and st.button("Research all contacts", type="primary", key="wb_research_all"):
        progress = st.progress(0, text="Researching…")
        ok = 0
        for i, contact in enumerate(missing):
            try:
                research_contact_for_job(contact_id=contact.id, job_id=job_id)
                ok += 1
            except PersonResearchError as exc:
                st.warning(f"{contact.full_name}: {exc}")
            progress.progress((i + 1) / len(missing), text=f"{i + 1}/{len(missing)}")
        st.success(f"Research complete — {ok}/{len(missing)} brief(s).")
        st.rerun()

    if st.button("Run research + outreach", key="wb_pipe_research"):
        opts = PipelineOptions(
            run_people=False,
            run_research=True,
            run_outreach=True,
            run_resume=False,
        )
        with st.spinner("Running research workers…"):
            for _node, _update in stream_pipeline_updates(job_id=job_id, options=opts):
                pass
        st.success("Research + outreach pipeline finished.")
        st.session_state["workbench_step"] = "outreach"
        st.rerun()

    st.divider()
    for contact in contacts:
        brief = contact.research_brief or {}
        hook = brief.get("outreach_hook") or brief.get("summary") or "No brief yet"
        title = f"{'✓' if contact.research_brief else '○'} {contact.full_name}"
        with st.expander(title):
            st.write(hook[:800] if isinstance(hook, str) else hook)
            if not contact.research_brief and st.button(
                "Research this contact", key=f"wb_res_one_{contact.id}"
            ):
                try:
                    research_contact_for_job(contact_id=contact.id, job_id=job_id)
                    st.success("Done")
                    st.rerun()
                except PersonResearchError as exc:
                    st.error(str(exc))
