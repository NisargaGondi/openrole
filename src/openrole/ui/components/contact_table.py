"""Table of discovered contacts for a job (Apollo + CareerShift)."""

from __future__ import annotations

import streamlit as st

from openrole.db.models import Company, Contact, Job
from openrole.db.repository import apply_careershift_email, delete_contact, list_contacts_for_job
from openrole.db.session import get_session_factory, session_scope
from openrole.schemas.contact import discovery_source_label
from openrole.scrapers import careershift_client

_COLS = [0.4, 1.85, 2.0, 1.2, 1.45, 0.85, 1.65, 0.75, 0.3]


def _tier_label(contact: Contact) -> str:
    meta = contact.metadata_json or {}
    tier = meta.get("tier")
    if tier:
        return str(tier).replace("_", " ").title()
    if contact.priority_reason:
        return contact.priority_reason.split(" · ")[0]
    return "—"


def _handle_delete(contact_id: str) -> None:
    with session_scope() as session:
        deleted = delete_contact(session, contact_id)
    if not deleted:
        st.error("Could not remove — contact not found.")
        return
    st.toast("Contact removed")
    st.rerun()


def _render_header() -> None:
    labels = ["#", "Name", "Title", "Location", "Email", "Source", "Why ranked", "Fetch", ""]
    cols = st.columns(_COLS, gap="small")
    for col, label in zip(cols, labels, strict=True):
        col.markdown(f"**{label}**" if label else "&nbsp;", unsafe_allow_html=True)


def _format_email_cell(contact: Contact) -> str:
    meta = contact.metadata_json or {}
    email = contact.email or "—"
    if meta.get("email_ai_generated") and contact.email:
        conf = meta.get("email_guess_confidence")
        title = f"AI-guessed ({conf}%)" if conf else "AI-guessed"
        return (
            f'{email} '
            f'<span title="{title}" style="font-size:0.7em;padding:1px 5px;'
            f'border-radius:4px;background:#e8f0fe;color:#1a56db;margin-left:4px;">AI</span>'
        )
    if meta.get("careershift_email_fetched_at") and contact.email:
        return (
            f'{email} '
            f'<span title="Fetched from CareerShift" style="font-size:0.7em;padding:1px 5px;'
            f'border-radius:4px;background:#e6f4ea;color:#137333;margin-left:4px;">CS</span>'
        )
    return email


def _render_row(contact: Contact, *, company_name: str | None) -> None:
    meta = contact.metadata_json or {}
    name = contact.full_name or "—"
    title = contact.title or "—"
    if len(title) > 48:
        title = title[:45] + "…"
    location = contact.location or "—"
    email = _format_email_cell(contact)
    source = discovery_source_label(meta)
    reason = contact.priority_reason or "—"
    if len(reason) > 72:
        reason = reason[:69] + "…"
    rank = contact.priority_rank if contact.priority_rank else "—"

    with st.container(border=True):
        cols = st.columns(_COLS, gap="small")
        cols[0].markdown(f'<span class="or-lib-cell">{rank}</span>', unsafe_allow_html=True)
        cols[1].markdown(f'<span class="or-lib-cell">{name}</span>', unsafe_allow_html=True)
        cols[2].markdown(f'<span class="or-lib-cell">{title}</span>', unsafe_allow_html=True)
        cols[3].markdown(f'<span class="or-lib-cell">{location}</span>', unsafe_allow_html=True)
        cols[4].markdown(f'<span class="or-lib-cell">{email}</span>', unsafe_allow_html=True)
        cols[5].markdown(f'<span class="or-lib-cell">{source}</span>', unsafe_allow_html=True)
        cols[6].markdown(f'<span class="or-lib-cell">{reason}</span>', unsafe_allow_html=True)
        if company_name:
            if cols[7].button(
                "↻ CS",
                key=f"ct_cs_row_{contact.id}",
                help="Fetch or refresh email from CareerShift (uses daily detail-view quota)",
            ):
                _fetch_careershift_email(contact.id, company_name=company_name, contact=contact)
        else:
            cols[7].markdown("&nbsp;", unsafe_allow_html=True)
        if cols[8].button("×", key=f"ct_del_{contact.id}", help="Remove this contact"):
            _handle_delete(contact.id)


def _render_detail(contact: Contact, *, company_name: str | None = None) -> None:
    meta = contact.metadata_json or {}
    st.markdown(f"**{contact.full_name}** · {_tier_label(contact)}")
    if contact.title:
        st.caption(contact.title)
    c1, c2, c3 = st.columns(3)
    c1.markdown(f"**Email:** {_format_email_cell(contact)}", unsafe_allow_html=True)
    c2.write(f"**Location:** {contact.location or '—'}")
    c3.write(f"**Source:** {discovery_source_label(meta)}")
    if contact.linkedin_url:
        st.link_button("LinkedIn profile", contact.linkedin_url, key=f"ct_li_{contact.id}")

    if company_name:
        if st.button(
            "Fetch email (CareerShift)",
            key=f"ct_cs_detail_{contact.id}",
            help="Fetch or replace email from CareerShift — works even if AI-guessed or already set",
        ):
            _fetch_careershift_email(contact.id, company_name=company_name, contact=contact)

    if contact.priority_reason:
        st.caption(contact.priority_reason)
    if contact.research_brief:
        with st.expander("Research brief", expanded=False):
            brief = contact.research_brief
            if isinstance(brief, dict):
                for key in ("summary", "recent_work", "suggested_hook", "tone_notes"):
                    if brief.get(key):
                        label = key.replace("_", " ").title()
                        st.markdown(f"**{label}:** {brief[key]}")
                angles = brief.get("outreach_angles") or []
                if angles:
                    st.markdown("**Outreach angles**")
                    for angle in angles:
                        st.markdown(f"- {angle}")
                signals = brief.get("public_signals") or []
                if signals:
                    st.markdown("**Public signals**")
                    for sig in signals:
                        if isinstance(sig, dict):
                            line = f"- [{sig.get('type', 'other')}] {sig.get('summary', '')}"
                            url = sig.get("url")
                            if url:
                                st.markdown(f"{line} — [{url}]({url})")
                            else:
                                st.markdown(line)
                points = brief.get("talking_points") or []
                if points:
                    st.markdown("**Talking points**")
                    for point in points:
                        st.markdown(f"- {point}")
                if brief.get("confidence") is not None:
                    st.caption(f"Confidence: {brief.get('confidence'):.0%}")
                layers = brief.get("layers_used") or []
                if layers:
                    st.caption(f"Sources: {', '.join(layers)}")
            else:
                st.write(brief)


def _fetch_careershift_email(contact_id: str, *, company_name: str, contact: Contact) -> None:
    with st.spinner("Searching CareerShift (browser)…"):
        result = careershift_client.fetch_contact_email(
            company_name=company_name,
            full_name=contact.full_name or "",
            title=contact.title,
        )
    if not result.get("ok"):
        st.warning(result.get("error", "CareerShift fetch failed"))
        return
    with session_scope() as session:
        saved = apply_careershift_email(
            session,
            contact_id,
            email=result["email"],
            fields=result.get("fields"),
        )
        session.commit()
    if saved is None:
        st.error("Could not save email to database.")
        return
    st.success(f"Email saved: {result['email']}")
    st.rerun()


def render_contact_table(job_id: str) -> int:
    """Show contacts discovered for this job. Returns contact count."""
    factory = get_session_factory()
    with factory() as session:
        job = session.get(Job, job_id)
        if not job or not job.company_id:
            st.info("No company linked to this job.")
            return 0
        company = session.get(Company, job.company_id)
        company_name = company.name if company else None
        contacts = list_contacts_for_job(
            session,
            company_id=job.company_id,
            source_job_id=job_id,
        )

    st.caption(f"**{len(contacts)}** contacts for this role")

    if not contacts:
        st.info(
            "No contacts yet — run **People** in Workbench with **Find people** checked, "
            "then return here to review results."
        )
        return 0

    st.markdown('<div class="or-data-table">', unsafe_allow_html=True)
    _render_header()
    for contact in contacts:
        _render_row(contact, company_name=company_name)
    st.markdown("</div>", unsafe_allow_html=True)

    labels = [
        f"#{c.priority_rank or '?'} — {c.full_name}"
        + (f" ({c.title[:40]}…)" if c.title and len(c.title) > 40 else f" ({c.title})" if c.title else "")
        for c in contacts
    ]
    id_by_label = {labels[i]: contacts[i].id for i in range(len(contacts))}
    pick = st.selectbox("Contact details", options=labels, key=f"ct_pick_{job_id}")
    selected = next(c for c in contacts if c.id == id_by_label[pick])
    st.divider()
    _render_detail(selected, company_name=company_name)
    return len(contacts)
