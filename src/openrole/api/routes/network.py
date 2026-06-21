"""Network contacts grouped by company with outreach drafts."""

from __future__ import annotations

from fastapi import APIRouter

from openrole.api.serialize import contact_to_dict, outreach_to_dict
from openrole.db.models import Contact, Job
from openrole.db.repository import (
    list_companies_for_network,
    list_contacts_for_company_network,
    list_outreach_drafts_for_company,
    list_visible_jobs_for_company,
)
from openrole.db.session import session_scope

router = APIRouter(tags=["network"])


@router.get("/network")
def network_by_company(limit_companies: int = 500):
    """Company-centric network view — not tied to the most recent N jobs."""
    cap = max(1, min(limit_companies, 1000))
    with session_scope() as session:
        companies_list = list_companies_for_network(session, limit=cap)
        job_title_by_id: dict[str, str] = {}
        companies: list[dict] = []

        for company in companies_list:
            cid = company.id
            contacts = list_contacts_for_company_network(session, cid)
            drafts = list_outreach_drafts_for_company(session, cid)
            jobs = list_visible_jobs_for_company(session, cid)

            for job in jobs:
                job_title_by_id[job.id] = job.title

            contact_by_id = {c.id: c for c in contacts}
            draft_payload = []
            for draft in drafts:
                contact = session.get(Contact, draft.contact_id) if draft.contact_id else None
                job_title = job_title_by_id.get(draft.job_id or "")
                if not job_title and draft.job_id:
                    job_row = session.get(Job, draft.job_id)
                    if job_row:
                        job_title = job_row.title
                        job_title_by_id[draft.job_id] = job_title
                draft_payload.append(
                    {
                        **outreach_to_dict(draft, contact or contact_by_id.get(draft.contact_id or "")),
                        "job_id": draft.job_id,
                        "job_title": job_title or None,
                    }
                )

            companies.append(
                {
                    "company_id": cid,
                    "company_name": company.name,
                    "company_domain": company.domain,
                    "jobs": [{"id": j.id, "title": j.title, "status": j.status.value} for j in jobs],
                    "contacts": [contact_to_dict(c) for c in contacts],
                    "drafts": draft_payload,
                }
            )

        total_contacts = sum(len(c["contacts"]) for c in companies)
        total_drafts = sum(len(c["drafts"]) for c in companies)
        total_roles = sum(len(c["jobs"]) for c in companies)
        alumni = sum(
            1
            for co in companies
            for contact in co["contacts"]
            if contact.get("is_cmu_alumni")
        )

        return {
            "companies": companies,
            "total_companies": len(companies),
            "total_roles": total_roles,
            "total_contacts": total_contacts,
            "total_drafts": total_drafts,
            "cmu_alumni_count": alumni,
        }
