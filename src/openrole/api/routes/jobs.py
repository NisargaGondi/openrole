"""Jobs CRUD + ingest."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from openrole.agents.job_ingestion import JobIngestionError, ingest_job
from openrole.api.activity_store import log as act_log
from openrole.api.serialize import contact_to_dict, job_to_dict, outreach_to_dict, pipeline_state_for_job
from openrole.db.models import Contact, JobStatus
from openrole.db.repository import (
    delete_job,
    get_job_with_company,
    list_contacts_for_job,
    list_jobs_for_tracker,
    list_outreach_drafts,
    update_job_status,
)
from openrole.db.session import session_scope

router = APIRouter(tags=["jobs"])


class IngestBody(BaseModel):
    job_url: str | None = None
    job_text: str | None = None


class StatusBody(BaseModel):
    status: str


@router.get("/jobs")
def list_jobs(limit: int = 200):
    with session_scope() as session:
        jobs = list_jobs_for_tracker(session, status="all", limit=limit)
        return {"jobs": [job_to_dict(j) for j in jobs]}


@router.get("/jobs/{job_id}")
def get_job(job_id: str):
    with session_scope() as session:
        job = get_job_with_company(session, job_id)
        if not job:
            raise HTTPException(404, "Job not found")
        contacts = (
            list_contacts_for_job(session, company_id=job.company_id, source_job_id=job_id)
            if job.company_id
            else []
        )
        drafts = list_outreach_drafts(session, job_id=job_id, limit=50)
        contact_by_id = {c.id: c for c in contacts}
        draft_payload = []
        for d in drafts:
            c = session.get(Contact, d.contact_id) if d.contact_id else None
            draft_payload.append(outreach_to_dict(d, c or contact_by_id.get(d.contact_id or "")))
        return {
            "job": job_to_dict(job),
            "contacts": [contact_to_dict(c) for c in contacts],
            "drafts": draft_payload,
            "draft_count": len(drafts),
            "pipeline": pipeline_state_for_job(job, contacts, draft_count=len(drafts)),
        }


@router.post("/jobs/ingest")
def ingest(body: IngestBody):
    act_log("Ingest started…", icon="radar")
    try:
        result = ingest_job(job_url=body.job_url, job_text=body.job_text)
    except JobIngestionError as exc:
        act_log(str(exc), level="err")
        raise HTTPException(400, str(exc)) from exc
    jid = result["job_id"]
    act_log(f"Saved role {jid[:8]}…", level="ok", icon="check")
    with session_scope() as session:
        job = get_job_with_company(session, jid)
        return {"job_id": jid, "job": job_to_dict(job) if job else None}


@router.delete("/jobs/{job_id}")
def remove_job(job_id: str):
    with session_scope() as session:
        if not delete_job(session, job_id):
            raise HTTPException(404, "Job not found")
    act_log(f"Removed role {job_id[:8]}…", level="warn")
    return {"deleted": True}


@router.patch("/jobs/{job_id}/status")
def patch_status(job_id: str, body: StatusBody):
    with session_scope() as session:
        try:
            job = update_job_status(session, job_id, JobStatus(body.status))
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"job": job_to_dict(job)}
