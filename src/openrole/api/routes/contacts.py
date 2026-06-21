"""Contact actions: delete, CareerShift email fetch."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from openrole.api.activity_store import log as act_log
from openrole.db.repository import apply_careershift_email, delete_contact
from openrole.db.models import Contact
from openrole.db.session import session_scope
from openrole.scrapers import careershift_client

router = APIRouter(tags=["contacts"])


class CareerShiftFetchBody(BaseModel):
    company_name: str | None = None


@router.delete("/contacts/{contact_id}")
def remove_contact(contact_id: str):
    with session_scope() as session:
        c = session.get(Contact, contact_id)
        name = c.full_name if c else contact_id[:8]
        if not delete_contact(session, contact_id):
            raise HTTPException(404, "Contact not found")
    act_log(f"Deleted contact {name}", level="warn", icon="alert")
    return {"deleted": True, "contact_id": contact_id}


@router.post("/contacts/{contact_id}/careershift-email")
def fetch_careershift_email(contact_id: str, body: CareerShiftFetchBody | None = None):
    with session_scope() as session:
        contact = session.get(Contact, contact_id)
        if not contact:
            raise HTTPException(404, "Contact not found")
        full_name = contact.full_name or ""
        title = contact.title
        display_name = contact.full_name or contact_id[:8]
        company_name = body.company_name if body and body.company_name else None
        if not company_name and contact.company_id:
            from openrole.db.models import Company

            company = session.get(Company, contact.company_id)
            company_name = company.name if company else None

    if not company_name:
        raise HTTPException(400, "company_name required")

    act_log(f"CareerShift fetch for {display_name}…", icon="radar")
    from openrole.scrapers.daemon_manager import managed_daemons

    with managed_daemons("careershift"):
        result = careershift_client.fetch_contact_email(
            company_name=company_name,
            full_name=full_name,
            title=title,
        )
    if not result.get("ok"):
        act_log(result.get("error", "CareerShift failed"), level="err", icon="alert")
        raise HTTPException(502, result.get("error", "CareerShift fetch failed"))

    with session_scope() as session:
        saved = apply_careershift_email(
            session,
            contact_id,
            email=result["email"],
            fields=result.get("fields"),
        )
        if not saved:
            raise HTTPException(500, "Could not save email")
    act_log(f"CareerShift email saved for {display_name}", level="ok", icon="check")
    return {"email": result["email"], "contact_id": contact_id}


@router.delete("/outreach/{outreach_id}")
def remove_outreach(outreach_id: str):
    from sqlalchemy import delete as sql_delete

    from openrole.db.models import Outreach

    with session_scope() as session:
        row = session.get(Outreach, outreach_id)
        if not row:
            raise HTTPException(404, "Draft not found")
        session.execute(sql_delete(Outreach).where(Outreach.id == outreach_id))
    act_log(f"Deleted outreach draft {outreach_id[:8]}…", level="warn", icon="alert")
    return {"deleted": True, "outreach_id": outreach_id}
