"""Person research: Tavily web evidence → Apollo facts → LLM synthesis brief."""

from __future__ import annotations

import json
import re
from typing import Any, Callable

from langchain_core.messages import HumanMessage, SystemMessage

from openrole.agents.outreach_prompts import resolve_contact_tier, tier_label
from openrole.agents.research_prompts import RESEARCH_SYNTHESIS_SYSTEM
from openrole.db.models import Contact, Job
from openrole.db.repository import save_research_brief
from openrole.db.session import session_scope
from openrole.llm import get_chat_model
from openrole.schemas.research import PersonResearchBrief, PublicSignal
from openrole.tools import apollo_client
from openrole.tools.web_search import extract_url, is_configured as tavily_ready
from openrole.tools.web_search import search_web

ProgressCallback = Callable[[str], None]

_RESEARCHER_TITLE = re.compile(r"\b(research|scientist|phd|professor|postdoc)\b", re.I)
_ENGINEER_TITLE = re.compile(r"\b(engineer|developer|software|ml|swe|sde|architect)\b", re.I)
_PLACEHOLDER_RE = re.compile(r"\[[^\]]+\]")
_LINKEDIN_SLUG_RE = re.compile(r"linkedin\.com/in/([\w\-_%]+)", re.I)
_BLOCKED_URL_RE = re.compile(
    r"(rocketreach|zoominfo|contactout|lusha|apollo\.io|signalhire|"
    r"linkedin\.com/pub/dir|linkedin\.com/directory)",
    re.I,
)
_MAX_WEB_SNIPPETS_CHARS = 12_000
_MAX_RESULTS_PER_QUERY = 4
_MAX_STORED_SOURCES = 5
_MIN_GOOD_SNIPPETS_FOR_SKIP_EXTRACT = 2


class PersonResearchError(Exception):
    pass


def research_contact_for_job(*, contact_id: str, job_id: str) -> dict[str, Any]:
    with session_scope() as session:
        contact = session.get(Contact, contact_id)
        job = session.get(Job, job_id)
        if contact is None or job is None:
            raise PersonResearchError("Contact or job not found")
        company_name = contact.company.name if contact.company else "Unknown"
        company_domain = contact.company.domain if contact.company else None
        brief = build_research_brief(
            contact=contact,
            job=job,
            company_name=company_name,
            company_domain=company_domain,
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

        contacts = dedupe_contacts_for_research(
            list_contacts_for_job(
                session,
                company_id=job.company_id,
                source_job_id=job_id,
            )[: limit * 2]
        )[:limit]
        results = []
        for contact in contacts:
            company_name = contact.company.name if contact.company else "Unknown"
            company_domain = contact.company.domain if contact.company else None
            brief = build_research_brief(
                contact=contact,
                job=job,
                company_name=company_name,
                company_domain=company_domain,
            )
            save_research_brief(session, contact.id, brief.to_db_dict())
            results.append({"contact_id": contact.id, "full_name": contact.full_name})
        session.commit()
        return {"status": "ok", "researched": len(results), "contacts": results}


def dedupe_contacts_for_research(contacts: list[Contact]) -> list[Contact]:
    """Drop duplicate people (same Apollo ID, LinkedIn slug, or matching name)."""
    sorted_contacts = sorted(contacts, key=_contact_research_sort_key)
    clusters: list[list[Contact]] = []

    for contact in sorted_contacts:
        matched = False
        for cluster in clusters:
            if _contacts_are_same_person(cluster[0], contact):
                cluster.append(contact)
                matched = True
                break
        if not matched:
            clusters.append([contact])

    return sorted(
        [min(cluster, key=_contact_research_sort_key) for cluster in clusters],
        key=_contact_research_sort_key,
    )


def _contacts_are_same_person(left: Contact, right: Contact) -> bool:
    meta_l = left.metadata_json or {}
    meta_r = right.metadata_json or {}
    ap_l = meta_l.get("apollo_person_id")
    ap_r = meta_r.get("apollo_person_id")
    if ap_l and ap_r and str(ap_l) == str(ap_r):
        return True

    slug_l = _linkedin_slug(left.linkedin_url)
    slug_r = _linkedin_slug(right.linkedin_url)
    if slug_l and slug_r and slug_l.lower() == slug_r.lower():
        return True

    fl, ll = _name_fingerprint(left.full_name or "")
    fr, lr = _name_fingerprint(right.full_name or "")
    if not fl or not fr or fl != fr:
        return False
    if not ll or not lr:
        return False
    return ll.startswith(lr) or lr.startswith(ll)


def _name_fingerprint(name: str) -> tuple[str, str]:
    parts = name.strip().split()
    if not parts:
        return "", ""
    first = re.sub(r"[^a-zA-Z]", "", parts[0]).lower()
    last_raw = parts[-1] if len(parts) > 1 else ""
    last_prefix = re.sub(r"\*.*", "", last_raw)
    last_prefix = re.sub(r"[^a-zA-Z]", "", last_prefix).lower()[:3]
    return first, last_prefix


def gather_research_evidence(
    *,
    contact: Contact,
    job: Job,
    company_name: str,
    company_domain: str | None = None,
    on_progress: ProgressCallback | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Collect Tavily/Apollo evidence without LLM synthesis (for batch mode)."""
    layers: list[str] = []
    raw_sources: list[dict[str, Any]] = []
    apollo_facts: dict[str, Any] = {}
    apollo_snapshot: dict[str, Any] = {}
    gaps: list[str] = []
    tavily_queries: list[str] = []

    def _progress(msg: str) -> None:
        if on_progress:
            on_progress(msg)

    meta = contact.metadata_json or {}
    apollo_id = meta.get("apollo_person_id")
    person: dict[str, Any] | None = None

    if apollo_id and apollo_client.is_configured():
        _progress(f"Apollo enrich: {contact.full_name}")
        try:
            person = apollo_client.match_person(apollo_id=str(apollo_id))
            apollo_snapshot = apollo_client.person_to_fields(person)
            apollo_facts = apollo_client.person_to_research_facts(person)
            layers.append("apollo")
        except apollo_client.ApolloError:
            gaps.append("Apollo enrich unavailable")

    if person is None and apollo_client.is_configured() and company_domain:
        _progress(f"Apollo lookup: {contact.full_name}")
        try:
            found = apollo_client.find_person_by_name(
                domain=company_domain,
                full_name=contact.full_name,
                title=contact.title,
            )
            if found and found.get("id"):
                person = apollo_client.match_person(apollo_id=str(found["id"]))
                apollo_snapshot = apollo_client.person_to_fields(person)
                apollo_facts = apollo_client.person_to_research_facts(person)
                layers.append("apollo_backfill")
        except apollo_client.ApolloError:
            gaps.append("Apollo name lookup unavailable")

    linkedin_url = contact.linkedin_url or apollo_facts.get("linkedin_url")
    linkedin_slug = _linkedin_slug(linkedin_url)

    web_snippets: list[dict[str, Any]] = []
    if tavily_ready():
        _progress(f"Tavily research: {contact.full_name}")
        web_snippets, tavily_queries = _gather_tavily_evidence(
            contact=contact,
            company_name=company_name,
            job=job,
            linkedin_slug=linkedin_slug,
        )
        if web_snippets:
            layers.append("tavily")
            raw_sources.extend(web_snippets)
        else:
            gaps.append("No Tavily web results — brief relies on Apollo/structured fields")
    else:
        gaps.append("TAVILY_API_KEY not set — skipping web research")

    good_snippet_count = len(
        _filter_web_snippets(
            web_snippets,
            company_name=company_name,
            linkedin_slug=linkedin_slug,
            contact_name=contact.full_name,
        )
    )
    if (
        tavily_ready()
        and linkedin_url
        and "linkedin.com/in/" in linkedin_url.lower()
        and good_snippet_count < _MIN_GOOD_SNIPPETS_FOR_SKIP_EXTRACT
    ):
        extracted = extract_url(linkedin_url, query=f"{contact.full_name} {company_name}")
        raw_content = str(extracted.get("raw_content") or "") if extracted else ""
        if _linkedin_extract_is_useful(raw_content):
            layers.append("linkedin_extract")
            snippet = {
                "title": "LinkedIn profile extract",
                "url": linkedin_url,
                "content": raw_content[:2500],
                "score": 1.0,
                "kind": "linkedin_profile",
            }
            raw_sources.append(snippet)
            web_snippets.append(snippet)

    filtered_snippets = _filter_web_snippets(
        web_snippets,
        company_name=company_name,
        linkedin_slug=linkedin_slug,
        contact_name=contact.full_name,
    )

    tier = resolve_contact_tier(contact)
    evidence = {
        "contact": {
            "name": contact.full_name,
            "title": contact.title or apollo_facts.get("title"),
            "email": contact.email or apollo_facts.get("email"),
            "location": contact.location or apollo_facts.get("location"),
            "linkedin": linkedin_url,
            "tier": tier.name,
            "tier_label": tier_label(tier),
            "priority_reason": contact.priority_reason,
        },
        "company": company_name,
        "target_job": {
            "title": job.title,
            "department": job.department,
            "locations": job.locations or [],
            "description_excerpt": (job.description or "")[:2000],
        },
        "apollo_facts": apollo_facts,
        "web_snippets": _trim_web_snippets(filtered_snippets),
        "gaps_prefill": gaps,
    }
    meta_out = {
        "layers": layers,
        "sources": _trim_sources_for_storage(filtered_snippets),
        "apollo_snapshot": _trim_apollo_snapshot(apollo_snapshot),
        "tavily_queries": tavily_queries,
        "gaps": gaps,
    }
    return evidence, meta_out


def build_research_brief(
    *,
    contact: Contact,
    job: Job,
    company_name: str,
    company_domain: str | None = None,
    on_progress: ProgressCallback | None = None,
) -> PersonResearchBrief:
    evidence, meta_out = gather_research_evidence(
        contact=contact,
        job=job,
        company_name=company_name,
        company_domain=company_domain,
        on_progress=on_progress,
    )
    gaps = list(meta_out.get("gaps") or [])
    layers = list(meta_out.get("layers") or [])
    filtered_snippets = evidence.get("web_snippets") or []

    def _progress(msg: str) -> None:
        if on_progress:
            on_progress(msg)

    _progress(f"Synthesizing brief: {contact.full_name}")
    brief_data = _synthesize_brief(evidence)
    if brief_data:
        layers.append("llm")
        brief_data = _clean_synthesis_output(brief_data)
    else:
        brief_data = _fallback_brief(evidence)
        gaps.extend(brief_data.get("gaps") or [])

    public_signals = _parse_public_signals(brief_data.get("public_signals"))
    apollo_facts = evidence.get("apollo_facts") or {}
    tier = resolve_contact_tier(contact)

    return PersonResearchBrief(
        contact_id=contact.id,
        full_name=contact.full_name,
        title=contact.title or apollo_facts.get("title"),
        company_name=company_name,
        summary=str(brief_data.get("summary") or ""),
        recent_work=str(brief_data.get("recent_work") or ""),
        public_signals=public_signals,
        outreach_angles=list(brief_data.get("outreach_angles") or [])[:6],
        talking_points=list(brief_data.get("talking_points") or [])[:6],
        suggested_hook=str(brief_data.get("suggested_hook") or ""),
        tone_notes=str(brief_data.get("tone_notes") or ""),
        gaps=list(dict.fromkeys(gaps + (brief_data.get("gaps") or [])))[:8],
        confidence=float(brief_data.get("confidence") or 0.5),
        layers_used=layers,
        sources=list(meta_out.get("sources") or [])[:5],
        apollo_snapshot=meta_out.get("apollo_snapshot") or {},
        tavily_queries=list(meta_out.get("tavily_queries") or []),
    )


def build_person_research_queries(
    *,
    full_name: str,
    company_name: str,
    title: str | None,
    job_title: str | None,
    linkedin_slug: str | None = None,
) -> list[dict[str, str]]:
    """Targeted Tavily queries for blogs, LinkedIn activity, research, and technical work."""
    name = full_name.strip()
    company = company_name.strip()
    title_l = (title or "").lower()
    queries: list[dict[str, str]] = []

    if linkedin_slug:
        queries.append(
            {
                "kind": "linkedin_profile",
                "query": f"site:linkedin.com/in/{linkedin_slug}",
            }
        )
        queries.append(
            {
                "kind": "linkedin_posts",
                "query": f'site:linkedin.com/posts "{name}" OR {linkedin_slug}',
            }
        )

    queries.extend(
        [
            {
                "kind": "linkedin",
                "query": f'"{name}" "{company}" site:linkedin.com/in',
            },
            {
                "kind": "writing",
                "query": f'"{name}" "{company}" blog OR article OR podcast OR interview OR talk',
            },
            {
                "kind": "company_role",
                "query": f'"{name}" "{company}" {title or job_title or "engineer"}',
            },
        ]
    )

    if _RESEARCHER_TITLE.search(title_l):
        queries.append(
            {
                "kind": "research",
                "query": f'"{name}" "{company}" research paper OR publication OR arxiv OR scholar',
            }
        )
    if _ENGINEER_TITLE.search(title_l):
        queries.append(
            {
                "kind": "technical",
                "query": f'"{name}" "{company}" github OR "open source" OR conference OR meetup',
            }
        )
    return queries


def _gather_tavily_evidence(
    *,
    contact: Contact,
    company_name: str,
    job: Job,
    linkedin_slug: str | None,
) -> tuple[list[dict[str, Any]], list[str]]:
    specs = build_person_research_queries(
        full_name=contact.full_name,
        company_name=company_name,
        title=contact.title,
        job_title=job.title,
        linkedin_slug=linkedin_slug,
    )
    seen_urls: set[str] = set()
    merged: list[dict[str, Any]] = []
    query_strings: list[str] = []

    for spec in specs:
        query = spec["query"]
        query_strings.append(query)
        rows = search_web(query, max_results=_MAX_RESULTS_PER_QUERY, search_depth="basic")
        for row in rows:
            url = (row.get("url") or "").strip()
            key = url.lower() if url else (row.get("title") or "")[:80]
            if key in seen_urls:
                continue
            seen_urls.add(key)
            merged.append({**row, "kind": spec["kind"], "query": query})

    return merged, query_strings


def _filter_web_snippets(
    snippets: list[dict[str, Any]],
    *,
    company_name: str,
    linkedin_slug: str | None,
    contact_name: str,
) -> list[dict[str, Any]]:
    company_l = company_name.lower()
    name_tokens = [t for t in re.sub(r"\*+", " ", contact_name.lower()).split() if len(t) > 2]
    kept: list[dict[str, Any]] = []

    for row in snippets:
        url = str(row.get("url") or "")
        content = str(row.get("content") or "")
        title = str(row.get("title") or "")
        blob = f"{url} {title} {content}".lower()

        if row.get("kind") == "linkedin_profile" and _linkedin_extract_is_useful(content):
            kept.append(row)
            continue

        if _BLOCKED_URL_RE.search(url):
            continue

        if url and "linkedin.com/pub/dir" in url.lower():
            continue

        if linkedin_slug and linkedin_slug.lower() in url.lower():
            kept.append(row)
            continue

        if company_l in blob:
            if not name_tokens or name_tokens[0] in blob:
                kept.append(row)
            continue

        if row.get("title") == "summary" and company_l in content.lower():
            kept.append(row)

    return kept


def _trim_web_snippets(snippets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep snippets within LLM context budget."""
    trimmed: list[dict[str, Any]] = []
    total = 0
    for row in snippets:
        content = str(row.get("content") or "")[:1500]
        chunk = {
            "kind": row.get("kind"),
            "title": row.get("title"),
            "url": row.get("url"),
            "content": content,
            "score": row.get("score"),
        }
        encoded = json.dumps(chunk)
        if total + len(encoded) > _MAX_WEB_SNIPPETS_CHARS:
            break
        trimmed.append(chunk)
        total += len(encoded)
    return trimmed


def _trim_sources_for_storage(snippets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Compact source list persisted on the contact brief."""
    stored: list[dict[str, Any]] = []
    for row in snippets[: _MAX_STORED_SOURCES]:
        stored.append(
            {
                "kind": row.get("kind"),
                "title": (row.get("title") or "")[:120],
                "url": row.get("url"),
            }
        )
    return stored


def _trim_apollo_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    if not snapshot:
        return {}
    trimmed = {k: v for k, v in snapshot.items() if k != "raw"}
    return trimmed


def _clean_synthesis_output(data: dict[str, Any]) -> dict[str, Any]:
    cleaned = dict(data)
    hook = str(cleaned.get("suggested_hook") or "")
    if _PLACEHOLDER_RE.search(hook):
        cleaned["suggested_hook"] = _PLACEHOLDER_RE.sub("", hook).strip(" ,—-")
    angles = cleaned.get("outreach_angles")
    if isinstance(angles, list):
        cleaned["outreach_angles"] = [
            _PLACEHOLDER_RE.sub("", str(a)).strip(" ,—-")
            for a in angles
            if str(a).strip() and not _PLACEHOLDER_RE.fullmatch(str(a).strip())
        ]
    return cleaned


def _synthesize_brief(evidence: dict[str, Any]) -> dict[str, Any] | None:
    try:
        model = get_chat_model(research=True, temperature=0.2)
    except RuntimeError:
        return None
    try:
        response = model.invoke(
            [
                SystemMessage(content=RESEARCH_SYNTHESIS_SYSTEM),
                HumanMessage(content=json.dumps(evidence)[:120_000]),
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


def _fallback_brief(evidence: dict[str, Any]) -> dict[str, Any]:
    contact = evidence.get("contact") or {}
    apollo = evidence.get("apollo_facts") or {}
    company = evidence.get("company") or "the company"
    title = contact.get("title") or apollo.get("title")
    talking_points = _fallback_talking_points(
        {
            "title": title,
            "company": company,
            "job_title": (evidence.get("target_job") or {}).get("title"),
            "job_locations": (evidence.get("target_job") or {}).get("locations") or [],
            "headline": apollo.get("headline"),
        }
    )
    return {
        "summary": apollo.get("headline")
        or (f"{contact.get('name')} — {title or 'contact'} at {company}"),
        "recent_work": title or "",
        "public_signals": [],
        "outreach_angles": talking_points[:3],
        "talking_points": talking_points,
        "suggested_hook": f"Your work as {title or 'a leader'} at {company}",
        "tone_notes": "Professional, concise, specific to the role.",
        "confidence": 0.35,
        "gaps": ["LLM synthesis unavailable — using Apollo/structured fields only"],
    }


def _parse_public_signals(raw: Any) -> list[PublicSignal]:
    if not isinstance(raw, list):
        return []
    signals: list[PublicSignal] = []
    allowed = {
        "linkedin_post",
        "blog",
        "talk",
        "paper",
        "github",
        "news",
        "other",
    }
    for row in raw:
        if not isinstance(row, dict):
            continue
        sig_type = str(row.get("type") or "other").lower()
        if sig_type not in allowed:
            sig_type = "other"
        summary = str(row.get("summary") or "").strip()
        if not summary:
            continue
        url = row.get("url")
        signals.append(
            PublicSignal(
                type=sig_type,  # type: ignore[arg-type]
                summary=summary,
                url=str(url) if url else None,
            )
        )
    return signals[:8]


def _fallback_talking_points(structured: dict[str, Any]) -> list[str]:
    points: list[str] = []
    if structured.get("headline"):
        points.append(f"Headline: {structured['headline']}")
    if structured.get("title"):
        points.append(f"Current role: {structured['title']} at {structured.get('company')}")
    if structured.get("job_title"):
        points.append(f"Target opening: {structured['job_title']}")
    if structured.get("job_locations"):
        points.append(f"Role locations: {', '.join(structured['job_locations'][:3])}")
    return points or ["Review LinkedIn profile before outreach"]


def _linkedin_slug(url: str | None) -> str | None:
    if not url:
        return None
    match = _LINKEDIN_SLUG_RE.search(url)
    return match.group(1).rstrip("/") if match else None


def _linkedin_extract_is_useful(content: str) -> bool:
    if not content or len(content) < 250:
        return False
    lower = content.lower()
    if lower.count("n/a") >= 4:
        return False
    none_activity = lower.count("none  \n[view post]")
    if none_activity >= 3:
        return False
    return True


def _contact_dedupe_key(contact: Contact) -> str | None:
    """Legacy key helper — prefer _contacts_are_same_person for clustering."""
    meta = contact.metadata_json or {}
    apollo_id = meta.get("apollo_person_id")
    if apollo_id:
        return f"apollo:{apollo_id}"
    slug = _linkedin_slug(contact.linkedin_url)
    if slug:
        return f"li:{slug.lower()}"
    first, last = _name_fingerprint(contact.full_name or "")
    if first:
        return f"name:{first}_{last}"
    return None


def _normalize_person_name(name: str) -> str:
    first, last = _name_fingerprint(name)
    return f"{first}_{last}" if first else ""


def _contact_research_sort_key(contact: Contact) -> tuple:
    """Prefer lower rank, full names, and LinkedIn URLs when deduping."""
    rank = contact.priority_rank if contact.priority_rank is not None else 999
    obfuscated = 1 if "*" in (contact.full_name or "") else 0
    has_li = 0 if contact.linkedin_url else 1
    return (rank, obfuscated, has_li, contact.full_name or "")

