"""Batch person research: gather evidence per contact, one LLM synthesis call."""

from __future__ import annotations

import json
import re
from typing import Any, Callable

from langchain_core.messages import HumanMessage, SystemMessage

from openrole.agents.person_research import (
    PersonResearchError,
    build_research_brief,
    gather_research_evidence,
)
from openrole.agents.research_prompts import BATCH_RESEARCH_SYNTHESIS_SYSTEM
from openrole.db.models import Contact, Job
from openrole.db.repository import save_research_brief
from openrole.db.session import session_scope
from openrole.llm import get_chat_model
from openrole.llm.tracking import llm_usage_context, model_label_for_role
from openrole.schemas.research import PersonResearchBrief

ProgressCallback = Callable[[str], None]


def research_contacts_batch(
    *,
    job_id: str,
    contact_ids: list[str],
    on_progress: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Tavily/Apollo per contact, then one batched LLM call for all briefs."""
    if not contact_ids:
        return {"status": "ok", "researched": 0, "research_briefs": []}

    def _log(msg: str) -> None:
        from openrole.api.pipeline_cancel import check_cancelled

        check_cancelled()
        if on_progress:
            on_progress(msg)

    from openrole.api.pipeline_cancel import check_cancelled

    results: list[dict[str, Any]] = []
    evidence_rows: list[dict[str, Any]] = []

    with session_scope() as session:
        job = session.get(Job, job_id)
        if job is None:
            raise PersonResearchError("Job not found")

        contacts: list[Contact] = []
        for cid in contact_ids:
            contact = session.get(Contact, cid)
            if contact:
                contacts.append(contact)

        if not contacts:
            raise PersonResearchError("No contacts found for batch research")

        _log(f"Gathering evidence for {len(contacts)} contact(s)…")
        for contact in contacts:
            check_cancelled()
            company_name = contact.company.name if contact.company else "Unknown"
            company_domain = contact.company.domain if contact.company else None
            try:
                evidence, layers_meta = gather_research_evidence(
                    contact=contact,
                    job=job,
                    company_name=company_name,
                    company_domain=company_domain,
                    on_progress=_log,
                )
                evidence_rows.append(
                    {
                        "contact_id": contact.id,
                        "full_name": contact.full_name,
                        "evidence": evidence,
                        "layers_meta": layers_meta,
                    }
                )
            except Exception as exc:
                _log(f"Evidence failed for {contact.full_name}: {exc}")
                brief = build_research_brief(
                    contact=contact,
                    job=job,
                    company_name=company_name,
                    company_domain=company_domain,
                    on_progress=_log,
                )
                saved = save_research_brief(session, contact.id, brief.to_db_dict())
                results.append(
                    {
                        "contact_id": contact.id,
                        "status": "ok",
                        "brief": saved.research_brief,
                        "fallback": True,
                    }
                )

        if evidence_rows:
            model_label = model_label_for_role(research=True)
            _log(f"[{model_label}] research synthesis · {len(evidence_rows)} contact(s)")
            briefs_by_id = _batch_synthesize(evidence_rows)
            for row in evidence_rows:
                cid = row["contact_id"]
                contact = next(c for c in contacts if c.id == cid)
                company_name = contact.company.name if contact.company else "Unknown"
                brief_data = briefs_by_id.get(cid) or briefs_by_id.get(contact.full_name.lower())
                if brief_data:
                    brief = _brief_from_batch_row(
                        contact=contact,
                        job=job,
                        company_name=company_name,
                        brief_data=brief_data,
                        layers_meta=row["layers_meta"],
                    )
                else:
                    brief = build_research_brief(
                        contact=contact,
                        job=job,
                        company_name=company_name,
                        company_domain=contact.company.domain if contact.company else None,
                        on_progress=_log,
                    )
                saved = save_research_brief(session, contact.id, brief.to_db_dict())
                results.append(
                    {"contact_id": contact.id, "status": "ok", "brief": saved.research_brief}
                )

        session.commit()

    _log(f"Research complete — {len(results)} brief(s)")
    return {"status": "ok", "researched": len(results), "research_briefs": results}


def _batch_synthesize(evidence_rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Return contact_id (or name key) -> brief dict."""
    try:
        model = get_chat_model(research=True, temperature=0.2)
    except RuntimeError:
        return {}

    payload = [
        {
            "contact_id": row["contact_id"],
            "full_name": row["full_name"],
            "evidence": row["evidence"],
        }
        for row in evidence_rows
    ]
    user = (
        f"Synthesize research briefs for {len(payload)} contacts. "
        f"Return one entry per contact_id.\n\n{json.dumps(payload, ensure_ascii=False)[:200_000]}"
    )
    try:
        with llm_usage_context(
            log_activity=True,
            detail=f"research synthesis · {len(payload)} contacts",
        ):
            response = model.invoke(
                [SystemMessage(content=BATCH_RESEARCH_SYNTHESIS_SYSTEM), HumanMessage(content=user)]
            )
        content = str(response.content).strip()
        if content.startswith("```"):
            content = re.sub(r"^```(?:json)?\s*", "", content)
            content = re.sub(r"\s*```$", "", content)
        data = json.loads(content)
    except Exception:
        return {}

    out: dict[str, dict[str, Any]] = {}
    for item in data.get("briefs") or []:
        if not isinstance(item, dict):
            continue
        cid = item.get("contact_id")
        if cid:
            out[str(cid)] = item
        name = str(item.get("full_name") or "").lower()
        if name:
            out[name] = item
    return out


def _brief_from_batch_row(
    *,
    contact: Contact,
    job: Job,
    company_name: str,
    brief_data: dict[str, Any],
    layers_meta: dict[str, Any],
) -> PersonResearchBrief:
    from openrole.agents.person_research import _clean_synthesis_output, _parse_public_signals

    brief_data = _clean_synthesis_output(brief_data)
    layers = list(layers_meta.get("layers") or [])
    layers.append("llm_batch")
    return PersonResearchBrief(
        contact_id=contact.id,
        full_name=contact.full_name,
        title=contact.title,
        company_name=company_name,
        summary=str(brief_data.get("summary") or ""),
        recent_work=str(brief_data.get("recent_work") or ""),
        public_signals=_parse_public_signals(brief_data.get("public_signals")),
        outreach_angles=list(brief_data.get("outreach_angles") or [])[:6],
        talking_points=list(brief_data.get("talking_points") or [])[:6],
        suggested_hook=str(brief_data.get("suggested_hook") or ""),
        tone_notes=str(brief_data.get("tone_notes") or ""),
        gaps=list(brief_data.get("gaps") or [])[:8],
        confidence=float(brief_data.get("confidence") or 0.5),
        layers_used=layers,
        sources=list(layers_meta.get("sources") or [])[:5],
        apollo_snapshot=layers_meta.get("apollo_snapshot") or {},
        tavily_queries=list(layers_meta.get("tavily_queries") or []),
    )
