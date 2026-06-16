"""Person research: Apollo enrich → LLM brief → Tavily web search."""

from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import select

from openrole.db.models import Contact, Job
from openrole.db.repository import save_research_brief
from openrole.db.session import session_scope
from openrole.llm import get_chat_model
from openrole.schemas.research import PersonResearchBrief
from openrole.tools import apollo_client
from openrole.tools.web_search import is_configured as tavily_ready
from openrole.tools.web_search import search_web


class PersonResearchError(Exception):
    pass


def research_contact_for_job(*, contact_id: str, job_id: str) -> dict[str, Any]:
    with session_scope() as session:
        contact = session.get(Contact, contact_id)
        job = session.get(Job, job_id)
        if contact is None or job is None:
            raise PersonResearchError("Contact or job not found")
        company_name = contact.company.name if contact.company else "Unknown"
        brief = build_research_brief(
            contact=contact,
            job=job,
            company_name=company_name,
        )
        saved = save_research_brief(session, contact_id, brief.to_db_dict())
        session.commit()
        return {"status": "ok", "contact_id": contact_id, "brief": saved.research_brief}


def research_top_contacts_for_job(*, job_id: str, limit: int = 5) -> dict[str, Any]:
    with session_scope() as session:
        job = session.get(Job, job_id)
        if job is None or not job.company_id:
            raise PersonResearchError("Job not found")
        from openrole.db.repository import list_contacts_for_job

        contacts = list_contacts_for_job(
            session,
            company_id=job.company_id,
            source_job_id=job_id,
        )[:limit]
        results = []
        for contact in contacts:
            company_name = contact.company.name if contact.company else "Unknown"
            brief = build_research_brief(contact=contact, job=job, company_name=company_name)
            save_research_brief(session, contact.id, brief.to_db_dict())
            results.append({"contact_id": contact.id, "full_name": contact.full_name})
        session.commit()
        return {"status": "ok", "researched": len(results), "contacts": results}


def build_research_brief(*, contact: Contact, job: Job, company_name: str) -> PersonResearchBrief:
    layers: list[str] = []
    sources: list[dict[str, Any]] = []
    apollo_snapshot: dict[str, Any] = {}
    gaps: list[str] = []

    meta = contact.metadata_json or {}
    apollo_id = meta.get("apollo_person_id")
    if apollo_id and apollo_client.is_configured():
        try:
            person = apollo_client.match_person(apollo_id=str(apollo_id))
            apollo_snapshot = apollo_client.person_to_fields(person)
            layers.append("apollo")
        except apollo_client.ApolloError:
            gaps.append("Apollo enrich unavailable")

    structured = {
        "name": contact.full_name,
        "title": contact.title or apollo_snapshot.get("title"),
        "email": contact.email or apollo_snapshot.get("email"),
        "location": contact.location or apollo_snapshot.get("location"),
        "linkedin": contact.linkedin_url or apollo_snapshot.get("linkedin_url"),
        "company": company_name,
        "job_title": job.title,
        "job_department": job.department,
        "job_locations": job.locations or [],
    }

    brief_data = _llm_brief(structured)
    if brief_data:
        layers.append("llm")
    else:
        brief_data = {
            "talking_points": _fallback_talking_points(structured),
            "suggested_hook": f"Your work as {structured.get('title') or 'a leader'} at {company_name}",
            "tone_notes": "Professional, concise, specific to the role.",
            "confidence": 0.35,
            "gaps": ["LLM unavailable — using structured fields only"],
        }
        gaps.extend(brief_data.get("gaps") or [])

    confidence = float(brief_data.get("confidence") or 0.5)
    if confidence < 0.55 and tavily_ready():
        web = search_web(
            f'"{contact.full_name}" "{company_name}" {job.title or "engineer"}',
            max_results=4,
        )
        if web:
            layers.append("tavily")
            sources.extend(web)
            web_brief = _llm_brief(
                {**structured, "web_snippets": json.dumps(web)[:4000]},
                web_mode=True,
            )
            if web_brief:
                brief_data["talking_points"] = web_brief.get("talking_points") or brief_data.get(
                    "talking_points", []
                )
                brief_data["suggested_hook"] = web_brief.get("suggested_hook") or brief_data.get(
                    "suggested_hook", ""
                )
                brief_data["confidence"] = max(confidence, float(web_brief.get("confidence") or 0.6))
                gaps = web_brief.get("gaps") or gaps

    return PersonResearchBrief(
        contact_id=contact.id,
        full_name=contact.full_name,
        title=contact.title,
        company_name=company_name,
        talking_points=list(brief_data.get("talking_points") or [])[:6],
        suggested_hook=str(brief_data.get("suggested_hook") or ""),
        tone_notes=str(brief_data.get("tone_notes") or ""),
        gaps=list(dict.fromkeys(gaps + (brief_data.get("gaps") or [])))[:8],
        confidence=float(brief_data.get("confidence") or 0.5),
        layers_used=layers,
        sources=sources[:10],
        apollo_snapshot=apollo_snapshot,
    )


def _llm_brief(context: dict[str, Any], *, web_mode: bool = False) -> dict[str, Any] | None:
    try:
        model = get_chat_model(writing=True, temperature=0.3)
    except RuntimeError:
        return None
    system = (
        "You help draft personalized job-search outreach research. "
        "Return ONLY JSON with keys: talking_points (array of 3-5 strings), "
        "suggested_hook (one sentence), tone_notes (short), confidence (0-1 float), "
        "gaps (array of missing info). Be factual; do not invent employers or publications."
    )
    if web_mode:
        system += " Use web_snippets when provided."
    try:
        response = model.invoke(
            [
                SystemMessage(content=system),
                HumanMessage(content=json.dumps(context)[:120_000]),
            ]
        )
        content = str(response.content).strip()
        if content.startswith("```"):
            content = re.sub(r"^```(?:json)?\s*", "", content)
            content = re.sub(r"\s*```$", "", content)
        data = json.loads(content)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _fallback_talking_points(structured: dict[str, Any]) -> list[str]:
    points = []
    if structured.get("title"):
        points.append(f"Current role: {structured['title']} at {structured.get('company')}")
    if structured.get("job_title"):
        points.append(f"Target opening: {structured['job_title']}")
    if structured.get("job_locations"):
        points.append(f"Role locations: {', '.join(structured['job_locations'][:3])}")
    return points or ["Review LinkedIn profile before outreach"]
