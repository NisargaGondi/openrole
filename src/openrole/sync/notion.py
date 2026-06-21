"""Push scout jobs to a Notion database."""

from __future__ import annotations

from typing import Any

import httpx

from openrole.config import get_settings
from openrole.db.models import Job
from openrole.sync.mappers import job_to_tracker_row

_NOTION_VERSION = "2022-06-28"
_BASE = "https://api.notion.com/v1"

TrackerRow = dict[str, Any]


def notion_configured() -> bool:
    s = get_settings()
    return bool(s.notion_api_key and s.notion_jobs_database_id)


def _headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Notion-Version": _NOTION_VERSION,
        "Content-Type": "application/json",
    }


def _page_properties(row: dict[str, Any], *, settings: Any | None = None) -> dict[str, Any]:
    from openrole.config import get_settings

    s = settings or get_settings()
    title = row.get("title") or "Untitled"
    company = row.get("company") or ""
    url = row.get("url") or ""
    score = row.get("relevance_score")
    props: dict[str, Any] = {
        s.notion_prop_title: {"title": [{"text": {"content": title[:2000]}}]},
    }
    if company and s.notion_prop_company:
        props[s.notion_prop_company] = {"rich_text": [{"text": {"content": company[:2000]}}]}
    if url and s.notion_prop_url:
        props[s.notion_prop_url] = {"url": url}
    if score is not None and s.notion_prop_score:
        props[s.notion_prop_score] = {"number": float(score)}
    status = row.get("status")
    if status and s.notion_prop_status:
        props[s.notion_prop_status] = {
            "select": {"name": str(status).replace("_", " ").title()[:100]}
        }
    source = row.get("scout_source")
    if source and s.notion_prop_source:
        props[s.notion_prop_source] = {"rich_text": [{"text": {"content": str(source)[:2000]}}]}
    opt = row.get("opt_status")
    if opt and s.notion_prop_opt:
        props[s.notion_prop_opt] = {"rich_text": [{"text": {"content": str(opt)[:2000]}}]}
    return props


def sync_tracker_rows_to_notion(rows: list[TrackerRow], *, dry_run: bool = False) -> dict[str, Any]:
    settings = get_settings()
    if not settings.notion_api_key or not settings.notion_jobs_database_id:
        return {"ok": False, "synced": 0, "error": "NOTION_API_KEY or NOTION_JOBS_DATABASE_ID not set"}

    synced = 0
    errors: list[str] = []
    page_ids: list[dict[str, str]] = []
    with httpx.Client(timeout=30.0) as client:
        for row in rows:
            if dry_run:
                synced += 1
                continue
            props = _page_properties(row, settings=settings)
            title = row.get("title") or "Untitled"
            existing_page = row.get("notion_page_id")
            try:
                if existing_page:
                    resp = client.patch(
                        f"{_BASE}/pages/{existing_page}",
                        headers=_headers(settings.notion_api_key),
                        json={"properties": props},
                    )
                else:
                    resp = client.post(
                        f"{_BASE}/pages",
                        headers=_headers(settings.notion_api_key),
                        json={
                            "parent": {"database_id": settings.notion_jobs_database_id},
                            "properties": props,
                        },
                    )
                if resp.status_code >= 400:
                    errors.append(f"{title}: {resp.status_code} {resp.text[:200]}")
                else:
                    synced += 1
                    page_id = resp.json().get("id")
                    job_id = row.get("job_id")
                    if page_id and job_id:
                        page_ids.append({"job_id": str(job_id), "page_id": str(page_id)})
            except Exception as exc:
                errors.append(f"{title}: {exc}")

    return {"ok": len(errors) == 0, "synced": synced, "errors": errors, "page_ids": page_ids}


def sync_job_status_to_notion(row: TrackerRow, *, notion_page_id: str) -> dict[str, Any]:
    """Update an existing Notion page when job status changes in OpenRole."""
    settings = get_settings()
    if not settings.notion_api_key:
        return {"ok": False, "error": "NOTION_API_KEY not set"}
    row = dict(row)
    row["notion_page_id"] = notion_page_id
    return sync_tracker_rows_to_notion([row])


def sync_jobs_to_notion(jobs: list[Job], *, dry_run: bool = False) -> dict[str, Any]:
    from openrole.db.repository import get_job_notion_page_id

    rows = []
    for job in jobs:
        row = job_to_tracker_row(job)
        page_id = get_job_notion_page_id(job)
        if page_id:
            row["notion_page_id"] = page_id
        rows.append(row)
    return sync_tracker_rows_to_notion(rows, dry_run=dry_run)
