"""LLM-assisted corporate email guessing when discovery sources return no email."""

from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from openrole.config import get_settings
from openrole.llm import get_chat_model
from openrole.schemas.contact import DiscoveredContact
from openrole.scrapers.email_utils import clean_email, is_placeholder_email

_SYSTEM = """You infer likely corporate work email addresses for employees when no verified email exists.

The candidate will use these ONLY for cold outreach — prefer conservative, high-confidence guesses.

Common patterns at tech companies (in order of likelihood):
1. first@domain — e.g. matthias@anthropic.com
2. first.last@domain — e.g. britt.olsson@anthropic.com
3. flast@domain — e.g. bjain@anthropic.com
4. firstl@domain — e.g. matthiasr@anthropic.com
5. last@domain — rare at large companies

Rules:
- ONLY use the provided company_domain (never example.com, gmail.com, or university domains).
- Use lowercase ASCII; strip accents from names when needed.
- Return one entry per person in the input list (same full_name).
- If the name is ambiguous or domain unknown, set confidence below 40 and omit email.
- confidence 70+ = strong pattern match; 50-69 = plausible; below 50 = omit email.

Return ONLY valid JSON:
{
  "emails": [
    {
      "full_name": "exact name from input",
      "email": "guess@company_domain",
      "confidence": 0-100,
      "pattern": "first@domain | first.last@domain | flast@domain | other"
    }
  ]
}
"""


def guess_emails_with_llm(
    contacts: list[DiscoveredContact],
    *,
    company_name: str,
    company_domain: str,
    min_confidence: int = 55,
) -> tuple[list[DiscoveredContact], list[str]]:
    """Fill missing emails in one batched LLM call; tags metadata email_ai_generated."""
    if not contacts or not company_domain or not get_settings().llm_configured:
        return contacts, []

    need = [
        c
        for c in contacts
        if not c.email
        and not is_placeholder_email(c.metadata_json.get("stored_email_raw"))
    ]
    if not need:
        return contacts, []

    model = get_chat_model(fast=True, temperature=0.0)
    payload = [
        {
            "full_name": c.full_name,
            "title": c.title,
            "company": company_name,
        }
        for c in need
    ]
    user = (
        f"Company: {company_name}\n"
        f"company_domain: {company_domain}\n\n"
        f"People without emails ({len(payload)} total — return all in one JSON list):\n"
        f"{json.dumps(payload, ensure_ascii=False)}"
    )

    warnings: list[str] = []
    try:
        response = model.invoke([SystemMessage(content=_SYSTEM), HumanMessage(content=user)])
        data = _parse_json(str(response.content))
    except Exception as exc:
        return contacts, [f"Email guess skipped: {exc}"]

    by_name = {row.get("full_name", "").lower(): row for row in data.get("emails") or []}
    domain = company_domain.lower().lstrip("@")
    guessed = 0

    for contact in need:
        row = by_name.get(contact.full_name.lower())
        if not row:
            continue
        confidence = int(row.get("confidence") or 0)
        if confidence < min_confidence:
            continue
        raw_email = str(row.get("email") or "").strip().lower()
        if not raw_email.endswith(f"@{domain}"):
            local = raw_email.split("@")[0] if "@" in raw_email else raw_email
            raw_email = f"{local}@{domain}"
        email = clean_email(raw_email)
        if not email:
            continue
        contact.email = email
        contact.metadata_json["email_ai_generated"] = True
        contact.metadata_json["email_guess_confidence"] = confidence
        contact.metadata_json["email_guess_pattern"] = row.get("pattern")
        contact.metadata_json["needs_email"] = False
        contact.metadata_json["email_actionable"] = True
        guessed += 1
        warnings.append(
            f"AI-guessed email for {contact.full_name} ({confidence}% — {row.get('pattern', 'pattern')})"
        )

    if guessed:
        warnings.insert(0, f"Batch email guess: {guessed}/{len(need)} contact(s) via {get_settings().fast_model_name()}")

    return contacts, warnings


def _parse_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    data = json.loads(text)
    return data if isinstance(data, dict) else {"emails": data}
