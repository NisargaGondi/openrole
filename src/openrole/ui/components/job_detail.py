"""Full job detail panel — description, scout metadata, links."""

from __future__ import annotations

from typing import Any

import streamlit as st

from openrole.db.models import JOB_STATUS_LABELS, Job
from openrole.ui.navigation import go_to_dashboard, go_to_workbench
from openrole.ui.util.description_render import render_job_description


def job_option_label(job: Job) -> str:
    company = job.company.name if job.company else "Unknown company"
    return f"{job.title} @ {company} · {job.id[:8]}"


def render_job_detail(job: Job, *, show_actions: bool = True) -> None:
    company = job.company.name if job.company else "—"
    domain = job.company.domain if job.company and job.company.domain else "—"
    scout: dict[str, Any] = (job.raw_payload or {}).get("scout") or {}
    domain_meta = (job.raw_payload or {}).get("domain_resolution") or {}
    fetch_meta = (job.raw_payload or {}).get("universal_fetch") or {}
    visa_meta: dict[str, Any] = (job.raw_payload or {}).get("llm_enrich") or {}

    st.markdown(f"### {job.title}")
    st.caption(
        f"**{company}** · {JOB_STATUS_LABELS.get(job.status.value, job.status.value)} · "
        f"Domain: `{domain}`"
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.markdown(f"**Department**  \n{job.department or '—'}")
    locs = ", ".join(job.locations or []) or "—"
    c2.markdown(f"**Locations**  \n{locs}")
    c3.markdown(f"**Source**  \n{job.source_platform or '—'}")
    visa_status = visa_meta.get("visa_status") or scout.get("opt_status")
    if visa_status == "eligible":
        c4.markdown("**CPT/OPT**  \n✅ Eligible")
    elif visa_status == "ineligible":
        c4.markdown("**CPT/OPT**  \n❌ Not eligible")
    elif visa_status == "unknown":
        c4.markdown("**CPT/OPT**  \n⚠️ Not mentioned")
    else:
        c4.markdown("**CPT/OPT**  \n—")

    if visa_meta:
        visa_bits: list[str] = []
        if visa_meta.get("accepts_cpt") is True:
            visa_bits.append("CPT")
        if visa_meta.get("accepts_opt") is True:
            visa_bits.append("OPT")
        if visa_meta.get("stem_opt_eligible") is True:
            visa_bits.append("STEM OPT")
        if visa_meta.get("will_sponsor") is True:
            visa_bits.append("Sponsorship")
        if visa_bits:
            st.caption(f"Visa signals: {', '.join(visa_bits)}")
        if visa_meta.get("visa_notes"):
            st.info(str(visa_meta["visa_notes"]))
        evidence = visa_meta.get("visa_evidence") or []
        if evidence:
            with st.expander("Visa/CPT/OPT evidence from posting", expanded=False):
                for item in evidence:
                    st.markdown(f"- {item}")

    link_cols = st.columns(2)
    if job.source_url:
        link_cols[0].link_button("View posting", job.source_url, use_container_width=True)
    if job.apply_url and job.apply_url != job.source_url:
        link_cols[1].link_button("Apply link", job.apply_url, use_container_width=True)

    if scout.get("opt_needs_verification"):
        st.caption("⚠️ OPT/sponsorship not confirmed in posting — verify before applying.")

    if scout:
        with st.expander("Scout match details", expanded=False):
            st.markdown(
                f"**Score:** {scout.get('relevance_score', '—')} · "
                f"**Source:** {scout.get('source', '—')} · "
                f"**Resume:** {scout.get('resume_label', '—')}"
            )
            if scout.get("opt_mention"):
                st.caption(f"OPT note: {scout['opt_mention']}")
            if scout.get("domain_warnings"):
                st.warning("; ".join(scout["domain_warnings"]))

    if domain_meta:
        st.caption(
            f"Domain resolved via **{domain_meta.get('source')}** "
            f"({domain_meta.get('confidence')})"
        )

    if fetch_meta:
        st.caption(
            f"Fetched via universal scraper ({fetch_meta.get('source')}, "
            f"{fetch_meta.get('chars', '?')} chars)"
        )

    render_job_description(job.description)

    meta_cols = st.columns(2)
    meta_cols[0].caption(f"Job ID: `{job.id}`")
    meta_cols[1].caption(
        f"Added {(job.created_at.isoformat()[:16] if job.created_at else '—')} · "
        f"Updated {(job.updated_at.isoformat()[:16] if job.updated_at else '—')}"
    )

    if show_actions:
        a1, a2 = st.columns(2)
        if a1.button("Open in Workbench", type="primary", key=f"detail_pipe_{job.id}"):
            go_to_workbench(job_id=job.id, step="people")
        if a2.button("Show on dashboard", key=f"detail_dash_{job.id}"):
            go_to_dashboard()
