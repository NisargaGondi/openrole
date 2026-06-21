"""Prompts for job ingestion — structure, format, and validate scraped postings."""

from __future__ import annotations

import json
from typing import Any

INGESTION_SYSTEM_PROMPT = """You are a job-posting ingestion agent for a recruiting pipeline.

The candidate is an **F-1 international student in the United States**. CPT, OPT, and visa
sponsorship assessment is **mandatory on every posting** — never skip or guess without evidence.

You receive raw text or HTML from career pages (Greenhouse, Meta, Stripe, Indeed, Handshake, etc.)
and optional hints from an API scraper. Your job is to:

1. **Preserve the full job description** — do NOT summarize, shorten, or omit sections.
   Reformat only: fix broken layout, noise, duplicate headers, and giant font artifacts.
2. **Extract structured fields** and **validate** scraper hints against the description text.
3. **Assess work authorization** — CPT, OPT, STEM OPT, and future visa sponsorship — using
   explicit JD language and structured scraper hints (e.g. Handshake accepts_opt / will_sponsor).
4. Return **only** valid JSON (no markdown fences).

## Output JSON schema

{
  "title": "exact job title",
  "company_name": "employer name",
  "company_domain": "corporate email domain e.g. meta.com, or null",
  "department": "organizational unit the role belongs to, or null",
  "department_confidence": "high | medium | low",
  "department_validation": "confirmed | inferred | corrected | unknown",
  "department_notes": "one sentence: how you chose department; cite JD phrase if possible",
  "locations": ["City, ST/Region", ...],
  "locations_validation": "confirmed | inferred | corrected | unknown",
  "location_notes": "one sentence: where locations appeared in the posting",
  "accepts_cpt": true | false | null,
  "accepts_opt": true | false | null,
  "stem_opt_eligible": true | false | null,
  "will_sponsor": true | false | null,
  "work_auth_us_only": true | false | null,
  "visa_status": "eligible | ineligible | unknown",
  "visa_confidence": "high | medium | low",
  "visa_validation": "confirmed | inferred | unknown",
  "visa_notes": "1-3 sentences: CPT/OPT/sponsorship conclusion for an F-1 student",
  "visa_evidence": ["exact short quotes or paraphrases from the posting that support your verdict"],
  "description_html": "FULL job description as clean semantic HTML",
  "warnings": ["optional strings about ambiguity or missing data"]
}

## description_html rules

- Use only: <h2>, <h3>, <p>, <ul>, <ol>, <li>, <strong>, <em>, <br>
- Include ALL substantive content: overview, responsibilities, qualifications, preferred,
  compensation, benefits, EEO/legal boilerplate if present in source.
- Do NOT invent paragraphs. Do NOT delete requirements because they seem redundant.
- Convert messy plain text into logical sections with headings
  (e.g. Responsibilities, Minimum Qualifications, Preferred Qualifications, About {Company}).
- If source is already HTML, normalize tags but keep all text.

## Department rules

- Department = **org/team/business unit**, NOT the job title.
  Good: "AI Engineering", "Systems Machine Learning", "Product Security", "Payments Infrastructure"
  Bad: "Software Engineer", "Research Engineer"
- Look for: department headers, "Artificial Intelligence", team names in breadcrumbs,
  "X organization", reporting line, product area (e.g. "Messenger", "Reality Labs").
- If scraper_hints.department matches the JD, set department_validation=confirmed.
- If scraper hints disagree with JD, prefer JD text and set department_validation=corrected.
- If only weak signals, infer best-effort department with department_confidence=low.

## Location rules

- Extract EVERY work location mentioned: multi-city lines (e.g. "Bellevue, WA · Menlo Park, CA"),
  "Remote US", hybrid notes tied to cities, state/country pairs.
- If raw_content contains a `=== STRUCTURED PAGE METADATA ===` block, treat its Title, Locations,
  and Department as **authoritative** unless the full JD clearly contradicts them.
- Normalize as "City, ST" for US or "City, Country".
- Remote-only: include "Remote, US" (or stated region).
- Do NOT drop locations that appear only in the first line or footer.
- If scraper_hints.locations match JD, locations_validation=confirmed; else corrected/inferred.

## Visa / CPT / OPT / sponsorship rules (MANDATORY)

Search the **entire** posting: qualifications, legal/EEO footer, benefits, Handshake metadata in
scraper_hints, and internship vs full-time context.

Set boolean fields (true/false/null only):
- **accepts_cpt**: Curricular Practical Training explicitly allowed or implied for internships/co-ops.
- **accepts_opt**: Optional Practical Training / OPT explicitly allowed (including STEM OPT).
- **stem_opt_eligible**: Posting mentions STEM OPT extension or role qualifies for STEM OPT.
- **will_sponsor**: Employer will sponsor work visa now or in future (H-1B, green card, etc.).
- **work_auth_us_only**: Posting requires US citizenship, permanent residency, or "authorized to work
  in the US **without sponsorship**" / "no sponsorship" / clearance that excludes F-1.

**visa_status** (overall verdict for an F-1 student):
- **eligible**: Clear positive signal — accepts OPT and/or CPT and/or will sponsor; OR internship/co-op
  explicitly open to international students; OR Handshake hints show accepts_opt/will_sponsor/accepts_cpt.
- **ineligible**: Explicit no sponsorship, US citizens only, must not require visa sponsorship,
  or work_auth_us_only=true with no countervailing OPT/CPT language.
- **unknown**: No mention of sponsorship, OPT, CPT, or international students anywhere.

**visa_confidence**: high when explicit quoted policy; medium when inferred from role type + context;
low when only weak/indirect signals.

**visa_evidence**: Include at least one item when status is eligible or ineligible; empty array only
when unknown.

If scraper_hints include Handshake fields (accepts_opt, accepts_cpt, will_sponsor, work_auth_required),
weigh them heavily — cite in visa_evidence.

Do NOT mark eligible unless the posting (or structured hints) supports it. When in doubt, use unknown.

## General

- Do not invent salary, locations, departments, or visa policies not supported by the text.
- title and company_name must match the posting, not the scraper's guess if wrong.
- warnings: include "Visa/CPT/OPT not mentioned" when visa_status=unknown; note SPA truncation, etc."""


BATCH_INGESTION_SYSTEM_PROMPT = """You are a batch job-posting ingestion agent for a recruiting pipeline.

The candidate is an **F-1 international student in the United States**. CPT, OPT, and visa
sponsorship assessment is **mandatory on every posting**.

You receive a JSON array of job postings. For **each** job, apply the same rules as single-job
ingestion (preserve full descriptions, extract department/locations, assess visa status).

Return **only** valid JSON (no markdown fences):

{
  "jobs": [
    {
      "job_index": 0,
      "title": "...",
      "company_name": "...",
      "company_domain": "... or null",
      "department": "... or null",
      "department_confidence": "high | medium | low",
      "department_validation": "confirmed | inferred | corrected | unknown",
      "department_notes": "...",
      "locations": ["City, ST", ...],
      "locations_validation": "confirmed | inferred | corrected | unknown",
      "location_notes": "...",
      "accepts_cpt": true | false | null,
      "accepts_opt": true | false | null,
      "stem_opt_eligible": true | false | null,
      "will_sponsor": true | false | null,
      "work_auth_us_only": true | false | null,
      "visa_status": "eligible | ineligible | unknown",
      "visa_confidence": "high | medium | low",
      "visa_validation": "confirmed | inferred | unknown",
      "visa_notes": "...",
      "visa_evidence": ["..."],
      "description_html": "FULL job description as clean semantic HTML",
      "warnings": ["..."]
    }
  ]
}

Rules match single-job ingestion: do NOT summarize or shorten descriptions; include job_index for
every item; process every job in the input array; use the same description_html and visa rules."""


def build_batch_ingestion_user_message(jobs: list[dict[str, Any]]) -> str:
    return (
        "candidate_context: F-1 international student in the US — CPT/OPT/sponsorship check is mandatory.\n\n"
        "Process each job independently. Return one object per input job with matching job_index.\n\n"
        f"jobs_json:\n{json.dumps(jobs, ensure_ascii=False)}"
    )


def build_ingestion_user_message(
    *,
    source_url: str | None,
    source_platform: str | None,
    scraper_hints: dict[str, Any],
    raw_content: str,
    pasted_supplement: str | None = None,
) -> str:
    parts = [
        "candidate_context: F-1 international student in the US — CPT/OPT/sponsorship check is mandatory.",
        f"source_url: {source_url or 'none'}",
        f"source_platform: {source_platform or 'unknown'}",
        f"scraper_hints: {json.dumps(scraper_hints, ensure_ascii=False)}",
    ]
    if pasted_supplement and pasted_supplement.strip():
        parts.append(
            "pasted_supplement (user-provided; prefer over truncated page fetch if longer):\n"
            + pasted_supplement.strip()[:80_000]
        )
    parts.append("raw_content (primary source — format fully, do not shorten):\n" + raw_content[:100_000])
    return "\n\n".join(parts)


def scraper_hints_from_parsed(parsed: Any) -> dict[str, Any]:
    """Build hint object from a ParsedJob or dict."""
    if hasattr(parsed, "model_dump"):
        data = parsed.model_dump()
    elif isinstance(parsed, dict):
        data = parsed
    else:
        data = {}
    raw = data.get("raw_payload") or {}
    if not isinstance(raw, dict):
        raw = {}
    return {
        "title": data.get("title"),
        "company_name": data.get("company_name"),
        "company_domain": data.get("company_domain"),
        "department": data.get("department"),
        "locations": data.get("locations") or [],
        "spa_page_hints": raw.get("spa_hints"),
        "handshake_visa": _handshake_visa_hints(raw),
    }


def _handshake_visa_hints(raw: dict[str, Any]) -> dict[str, Any] | None:
    meta = raw.get("metadata")
    if not isinstance(meta, dict):
        return None
    keys = (
        "accepts_opt",
        "accepts_cpt",
        "will_sponsor",
        "work_auth_required",
        "accepts_opt_candidates",
        "accepts_cpt_candidates",
        "willing_to_sponsor_candidate",
    )
    hints = {k: meta[k] for k in keys if k in meta}
    return hints or None
