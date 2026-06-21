"""LLM relevance scoring for discovered contacts."""

from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from openrole.config import get_settings
from openrole.db.models import Job
from openrole.llm import get_chat_model
from openrole.schemas.contact import ContactTier, DiscoveredContact
from openrole.schemas.job_context import JobSearchContext

_SYSTEM = """You score contacts for outreach about a specific job opening.

The candidate is an F-1 student seeking referrals and hiring-manager intros at the target company.
Prioritize people who work in the SAME department/team as the job (engineers, researchers, alumni).
Hiring managers outside the department are lower value. Unrelated executives/recruiters are low value.

Return ONLY valid JSON with one score object per contact in the input list:
{
  "scores": [
    {
      "full_name": "exact name from input",
      "relevance": 0-100,
      "in_target_department": true|false,
      "contact_type": "team_engineer|hiring_manager|recruiter|alumni|unrelated",
      "rationale": "one short sentence"
    }
  ]
}

Scoring guide:
- 85-100: clear department match (title mentions team/department keywords)
- 60-84: plausible engineer/researcher at company, weak dept signal
- 30-59: recruiter, tangential role, or unknown dept
- 0-29: unrelated function (marketing, procurement, policy, etc.)
"""


def score_contacts_with_llm(
    contacts: list[DiscoveredContact],
    *,
    job: Job,
    search_context: JobSearchContext,
    company_name: str,
    linkedin_hints: str | None = None,
) -> tuple[list[DiscoveredContact], list[str]]:
    """Adjust relevance scores using LLM (ranking only — validation applies hard cuts)."""
    if not contacts or not get_settings().llm_configured:
        return contacts, []

    model = get_chat_model(research=True, temperature=0.1)
    payload = [
        {
            "full_name": c.full_name,
            "title": c.title,
            "tier": c.tier.name if hasattr(c.tier, "name") else str(c.tier),
            "location": c.location,
            "current_relevance": c.relevance_score,
        }
        for c in contacts
    ]
    user = (
        f"Company: {company_name}\n"
        f"Job title: {job.title}\n"
        f"Department: {search_context.department_name or job.department}\n"
        f"Department keywords: {search_context.expanded_department_queries()}\n"
        f"Job locations: {search_context.office_locations}\n\n"
    )
    if linkedin_hints:
        user += f"LinkedIn search hints (titles seen on public profiles):\n{linkedin_hints}\n\n"
    user += (
        f"Contacts ({len(payload)} total — score every person in one JSON list):\n"
        f"{json.dumps(payload, ensure_ascii=False)}"
    )

    try:
        response = model.invoke([SystemMessage(content=_SYSTEM), HumanMessage(content=user)])
        data = _parse_json(str(response.content))
    except Exception as exc:
        return contacts, [f"LLM contact scoring skipped: {exc}"]

    scores = {row.get("full_name", "").lower(): row for row in data.get("scores") or []}
    warnings: list[str] = []
    kept: list[DiscoveredContact] = []

    for contact in contacts:
        row = scores.get(contact.full_name.lower())
        if not row:
            kept.append(contact)
            continue

        llm_score = int(row.get("relevance") or 0)
        in_dept = bool(row.get("in_target_department"))
        contact.metadata_json["llm_relevance"] = llm_score
        contact.metadata_json["llm_in_target_department"] = in_dept
        contact.metadata_json["llm_contact_type"] = row.get("contact_type")
        contact.metadata_json["llm_rationale"] = row.get("rationale")

        recruiters = contact.tier in (
            ContactTier.ROLE_RECRUITER,
            ContactTier.GENERAL_RECRUITER,
            ContactTier.CMU_ALUMNI,
        )
        if llm_score < 25 and not recruiters:
            warnings.append(
                f"LLM low score for {contact.full_name}: {row.get('rationale', 'low relevance')}"
            )

        contact.relevance_score = int(contact.relevance_score * 0.55 + llm_score * 4.5)
        if in_dept:
            contact.relevance_score += 80
        kept.append(contact)

    return kept, warnings


def _parse_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    data = json.loads(text)
    return data if isinstance(data, dict) else {"scores": data}
