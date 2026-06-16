"""Resolve company email domain from ingestion context and external lookups."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from openrole.config import get_settings
from openrole.tools import apollo_client
from openrole.tools.web_search import is_configured as tavily_configured
from openrole.tools.web_search import search_web

_GENERIC_DOMAINS = frozenset(
    {
        "linkedin.com",
        "indeed.com",
        "glassdoor.com",
        "greenhouse.io",
        "lever.co",
        "ashbyhq.com",
        "myworkdayjobs.com",
        "workday.com",
        "joinhandshake.com",
        "app.careershift.com",
    }
)


@dataclass(frozen=True)
class DomainResolution:
    domain: str
    source: str
    confidence: str  # confirmed | inferred | guessed


def resolve_company_domain(
    *,
    company_name: str,
    existing_domain: str | None = None,
    source_url: str | None = None,
    description: str | None = None,
    raw_payload: dict[str, Any] | None = None,
) -> DomainResolution | None:
    """Best-effort company domain for Apollo people search."""
    if existing_domain:
        clean = apollo_client.normalize_domain(existing_domain)
        if _is_plausible_domain(clean):
            return DomainResolution(clean, "provided", "confirmed")

    for candidate in _candidates_from_url(source_url):
        if _is_plausible_domain(candidate):
            return DomainResolution(candidate, "source_url", "inferred")

    for candidate in _candidates_from_text(description or ""):
        if _is_plausible_domain(candidate):
            return DomainResolution(candidate, "description", "inferred")

    if raw_payload:
        for key in ("company_domain", "domain", "website", "companyWebsite"):
            val = raw_payload.get(key)
            if isinstance(val, str):
                d = apollo_client.normalize_domain(val)
                if _is_plausible_domain(d):
                    return DomainResolution(d, f"payload.{key}", "inferred")

    apollo_domain = _resolve_via_apollo(company_name)
    if apollo_domain:
        return DomainResolution(apollo_domain, "apollo", "inferred")

    web_domain = _resolve_via_web(company_name)
    if web_domain:
        return DomainResolution(web_domain, "tavily", "inferred")

    llm_domain = _resolve_via_llm(company_name, source_url=source_url, description=description)
    if llm_domain:
        return DomainResolution(llm_domain, "llm", "inferred")

    guessed = _guess_from_company_name(company_name)
    if guessed:
        return DomainResolution(guessed, "name_heuristic", "guessed")

    return None


def enrich_parsed_job_domain(parsed) -> tuple[Any, list[str]]:
    """Fill missing company_domain on a ParsedJob; returns (parsed, warnings)."""
    warnings: list[str] = []
    if parsed.company_domain:
        parsed.company_domain = apollo_client.normalize_domain(parsed.company_domain)
        return parsed, warnings

    resolution = resolve_company_domain(
        company_name=parsed.company_name,
        source_url=parsed.source_url,
        description=parsed.description,
        raw_payload=parsed.raw_payload,
    )
    if resolution is None:
        warnings.append(
            f"Could not resolve email domain for {parsed.company_name}. "
            "Add domain manually on the Saved jobs page before Find people."
        )
        return parsed, warnings

    parsed.company_domain = resolution.domain
    meta = dict(parsed.raw_payload or {})
    meta["domain_resolution"] = {
        "domain": resolution.domain,
        "source": resolution.source,
        "confidence": resolution.confidence,
    }
    parsed.raw_payload = meta
    if resolution.confidence == "guessed":
        warnings.append(
            f"Guessed company domain `{resolution.domain}` from company name — verify before outreach."
        )
    elif resolution.source != "provided":
        warnings.append(
            f"Inferred company domain `{resolution.domain}` via {resolution.source}."
        )
    return parsed, warnings


def _resolve_via_apollo(company_name: str) -> str | None:
    if not apollo_client.is_configured():
        return None
    try:
        org = apollo_client.search_organization(company_name=company_name)
    except Exception:
        org = {}
    domain = (org or {}).get("primary_domain") or (org or {}).get("domain")
    if domain and _is_plausible_domain(apollo_client.normalize_domain(str(domain))):
        return apollo_client.normalize_domain(str(domain))

    slug = re.sub(r"[^a-z0-9]+", "", company_name.lower())
    if len(slug) < 3:
        return None
    for guess in (f"{slug}.com", f"{slug}.io", f"{slug}.co"):
        try:
            org = apollo_client.enrich_organization(domain=guess)
        except Exception:
            continue
        if org.get("primary_domain") or org.get("id"):
            resolved = org.get("primary_domain") or guess
            if _is_plausible_domain(apollo_client.normalize_domain(str(resolved))):
                return apollo_client.normalize_domain(str(resolved))
    return None


def _resolve_via_web(company_name: str) -> str | None:
    if not tavily_configured():
        return None
    rows = search_web(f"{company_name} official company website domain", max_results=5)
    for row in rows:
        for text in (row.get("content") or "", row.get("url") or ""):
            for match in re.finditer(r"([a-z0-9][-a-z0-9]*\.(?:com|io|co|ai|net|org))", text.lower()):
                domain = match.group(1)
                if _is_plausible_domain(domain) and company_name.split()[0].lower() in domain:
                    return domain
        url = row.get("url") or ""
        if url:
            host = urlparse(url).netloc.lower().removeprefix("www.")
            if _is_plausible_domain(host) and not host.endswith("wikipedia.org"):
                if company_name.split()[0].lower() in host:
                    return host
    return None


def _resolve_via_llm(
    company_name: str,
    *,
    source_url: str | None,
    description: str | None,
) -> str | None:
    settings = get_settings()
    if not settings.llm_configured:
        return None
    try:
        from langchain_core.messages import HumanMessage, SystemMessage

        from openrole.llm import get_chat_model

        context_parts = [f"Company: {company_name}"]
        if source_url:
            context_parts.append(f"Job URL: {source_url}")
        if description:
            context_parts.append(f"Description excerpt: {description[:2000]}")
        if tavily_configured():
            snippets = search_web(f"{company_name} corporate website", max_results=3)
            if snippets:
                context_parts.append("Web snippets: " + json.dumps(snippets[:3])[:3000])

        model = get_chat_model(ingestion=True, temperature=0)
        system = (
            "Return ONLY valid JSON: {\"company_domain\": \"example.com\" or null}. "
            "Pick the primary corporate email domain for employee addresses. "
            "Do not use job board domains (linkedin, greenhouse, workday, etc.)."
        )
        response = model.invoke(
            [SystemMessage(content=system), HumanMessage(content="\n".join(context_parts))]
        )
        content = str(response.content).strip()
        if content.startswith("```"):
            content = re.sub(r"^```(?:json)?\s*", "", content)
            content = re.sub(r"\s*```$", "", content)
        data = json.loads(content)
        domain = data.get("company_domain")
        if domain and _is_plausible_domain(apollo_client.normalize_domain(str(domain))):
            return apollo_client.normalize_domain(str(domain))
    except Exception:
        return None
    return None


def _candidates_from_url(url: str | None) -> list[str]:
    if not url:
        return []
    host = urlparse(url).netloc.lower().removeprefix("www.")
    if not host or host in _GENERIC_DOMAINS:
        return []
    parts = host.split(".")
    if len(parts) >= 2 and parts[-2] in ("greenhouse", "lever", "ashbyhq", "myworkdayjobs"):
        return []
    if _is_plausible_domain(host):
        return [host]
    return []


def _candidates_from_text(text: str) -> list[str]:
    found: list[str] = []
    for match in re.finditer(r"@([a-z0-9][-a-z0-9.]*\.[a-z]{2,})", text.lower()):
        domain = match.group(1)
        if _is_plausible_domain(domain):
            found.append(domain)
    for match in re.finditer(r"https?://(?:www\.)?([a-z0-9][-a-z0-9.]*\.[a-z]{2,})", text.lower()):
        domain = match.group(1)
        if _is_plausible_domain(domain):
            found.append(domain)
    return found


def _guess_from_company_name(company_name: str) -> str | None:
    slug = re.sub(r"[^a-z0-9]+", "", company_name.lower())
    if len(slug) < 3:
        return None
    guess = f"{slug}.com"
    return guess if _is_plausible_domain(guess) else None


def _is_plausible_domain(domain: str) -> bool:
    d = domain.strip().lower()
    if not d or "." not in d or d in _GENERIC_DOMAINS:
        return False
    if any(d.endswith(f".{g}") or d == g for g in _GENERIC_DOMAINS):
        return False
    if d.endswith(".edu"):
        return False
    return bool(re.match(r"^[a-z0-9][-a-z0-9.]*\.[a-z]{2,}$", d))
