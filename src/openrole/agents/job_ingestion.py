"""Ingest job postings from URLs or pasted descriptions."""

from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from openrole.config import get_settings
from openrole.db.repository import save_parsed_job
from openrole.llm.vertex import get_chat_model
from openrole.schemas.job import ParsedJob
from openrole.scrapers.ats_apis import fetch_from_ats
from openrole.scrapers.page_meta import fetch_page_title, parse_linkedin_title
from openrole.scrapers.url_detect import JobPlatform, JobUrlInfo, detect_job_url
from openrole.tools import jobspy_client


class JobIngestionError(Exception):
    pass


def ingest_job(*, job_url: str | None = None, job_text: str | None = None) -> dict[str, Any]:
    if not job_url and not job_text:
        raise JobIngestionError("Provide a job URL or pasted job description")

    parsed: ParsedJob
    warnings: list[str] = []

    if job_url:
        parsed, warnings = _ingest_from_url(job_url.strip(), job_text)
    else:
        parsed = _ingest_from_text(job_text or "")

    job, company = save_parsed_job(parsed)
    return {
        "status": "ok",
        "job_id": job.id,
        "company_id": company.id,
        "parsed_job": parsed.model_dump(mode="json"),
        "warnings": warnings,
    }


def _ingest_from_url(url: str, fallback_text: str | None) -> tuple[ParsedJob, list[str]]:
    info = detect_job_url(url)
    warnings: list[str] = []

    if info.platform in (JobPlatform.GREENHOUSE, JobPlatform.LEVER, JobPlatform.ASHBY):
        return fetch_from_ats(info), warnings

    if info.platform == JobPlatform.LINKEDIN:
        title, company = None, None
        page_title = fetch_page_title(url)
        if page_title:
            title, company = parse_linkedin_title(page_title)
        if fallback_text and (not title or not company):
            extracted = _extract_with_llm(fallback_text, source_url=url)
            title = title or extracted.title
            company = company or extracted.company_name
        try:
            parsed = jobspy_client.fetch_linkedin_by_search(
                company=company,
                title=title,
                linkedin_job_id=info.job_id,
                source_url=url,
            )
            warnings.append(
                "LinkedIn matched via JobSpy search; verify title/company if results look wrong."
            )
            return parsed, warnings
        except Exception as exc:
            if fallback_text:
                return _extract_with_llm(fallback_text, source_url=url), [
                    f"JobSpy failed ({exc}); used pasted text instead."
                ]
            raise JobIngestionError(
                "LinkedIn ingestion failed. Paste the full job description below and retry."
            ) from exc

    if info.platform == JobPlatform.INDEED:
        try:
            return (
                jobspy_client.fetch_indeed_by_search(
                    indeed_job_id=info.job_id,
                    source_url=url,
                ),
                ["Indeed matched via JobSpy search; verify the listing."],
            )
        except Exception as exc:
            if fallback_text:
                return _extract_with_llm(fallback_text, source_url=url), [
                    f"JobSpy failed ({exc}); used pasted text."
                ]
            raise JobIngestionError("Indeed ingestion failed. Paste the job description.") from exc

    if info.platform == JobPlatform.WORKDAY:
        if fallback_text:
            parsed = _extract_with_llm(fallback_text, source_url=url)
            return parsed, ["Workday scraper not implemented; parsed from pasted text."]
        raise JobIngestionError(
            "Workday URLs need a pasted job description for now (Playwright scraper coming later)."
        )

    if info.platform == JobPlatform.HANDSHAKE:
        if fallback_text:
            parsed = _extract_with_llm(fallback_text, source_url=url)
            parsed.source_platform = JobPlatform.HANDSHAKE.value
            return parsed, ["Handshake API/MCP not wired in graph yet; parsed from pasted text."]
        raise JobIngestionError(
            "Handshake job URL requires pasted description until MCP integration is added."
        )

    if fallback_text:
        return _extract_with_llm(fallback_text, source_url=url), [
            f"Unknown platform ({info.platform.value}); parsed from pasted text."
        ]
    raise JobIngestionError(
        "Could not detect job board. Paste the job description or use a Greenhouse/Lever/Ashby URL."
    )


def _ingest_from_text(text: str) -> ParsedJob:
    cleaned = text.strip()
    if not cleaned:
        raise JobIngestionError("Job description text is empty")
    if get_settings().vertex_configured:
        return _extract_with_llm(cleaned)
    return _heuristic_parse(cleaned)


def _extract_with_llm(text: str, source_url: str | None = None) -> ParsedJob:
    model = get_chat_model()
    system = (
        "Extract job posting fields from the user content. "
        "Return ONLY valid JSON with keys: "
        "title, company_name, company_domain (nullable), department (nullable), "
        "locations (array of strings), description (full text, nullable). "
        "Do not invent facts not present in the text."
    )
    response = model.invoke(
        [SystemMessage(content=system), HumanMessage(content=text[:120_000])]
    )
    content = str(response.content)
    payload = _parse_json_from_llm(content)
    return ParsedJob(
        title=payload.get("title") or "Unknown role",
        company_name=payload.get("company_name") or "Unknown company",
        description=payload.get("description") or text,
        department=payload.get("department"),
        locations=payload.get("locations") or [],
        company_domain=payload.get("company_domain"),
        source_url=source_url,
        source_platform="text" if not source_url else detect_job_url(source_url).platform.value,
        apply_url=source_url,
        raw_payload={"llm_extract": payload},
    )


def _heuristic_parse(text: str) -> ParsedJob:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    title = lines[0][:512] if lines else "Unknown role"
    company = "Unknown company"
    for line in lines[:10]:
        if line.lower().startswith("company:"):
            company = line.split(":", 1)[1].strip()
            break
    return ParsedJob(
        title=title,
        company_name=company,
        description=text,
        source_platform="text",
        raw_payload={"heuristic": True},
    )


def _parse_json_from_llm(content: str) -> dict[str, Any]:
    content = content.strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise JobIngestionError("LLM returned invalid JSON for job extraction") from exc
    if not isinstance(data, dict):
        raise JobIngestionError("LLM job extraction must be a JSON object")
    return data
