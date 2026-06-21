"""Export scout jobs to CSV (and optional Google Sheets when configured)."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from openrole.config import _REPO_ROOT, get_settings
from openrole.db.models import Job
from openrole.sync.mappers import job_to_tracker_row

_CSV_PATH = _REPO_ROOT / "data" / "job_tracker.csv"
_FIELDNAMES = [
    "job_id",
    "title",
    "company",
    "url",
    "platform",
    "status",
    "relevance_score",
    "scout_source",
    "search_term",
    "run_id",
    "discovered_at",
]


def sheets_configured() -> bool:
    s = get_settings()
    raw = (getattr(s, "google_sheets_credentials_json", None) or "").strip()
    return bool(raw)


def _row_key(row: dict[str, Any]) -> str:
    job_id = (row.get("job_id") or "").strip()
    if job_id:
        return f"id:{job_id}"
    url = (row.get("url") or "").strip()
    if url:
        return f"url:{url}"
    return f"title:{row.get('title')}:{row.get('company')}"


def upsert_tracker_rows_to_csv(rows: list[dict[str, Any]], *, path: Path | None = None) -> Path:
    """Merge rows into CSV by job_id or url (no duplicate lines)."""
    target = path or _CSV_PATH
    target.parent.mkdir(parents=True, exist_ok=True)

    merged: dict[str, dict[str, Any]] = {}
    if target.is_file() and target.stat().st_size > 0:
        with target.open(newline="", encoding="utf-8") as fh:
            for existing in csv.DictReader(fh):
                merged[_row_key(existing)] = {k: existing.get(k, "") for k in _FIELDNAMES}

    for row in rows:
        normalized = {k: row.get(k, "") for k in _FIELDNAMES}
        merged[_row_key(normalized)] = normalized

    with target.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=_FIELDNAMES)
        writer.writeheader()
        for row in merged.values():
            writer.writerow(row)
    return target


def export_tracker_rows_to_csv(rows: list[dict[str, Any]], *, path: Path | None = None) -> Path:
    return upsert_tracker_rows_to_csv(rows, path=path)


def export_jobs_to_csv(jobs: list[Job], *, path: Path | None = None) -> Path:
    return upsert_tracker_rows_to_csv([job_to_tracker_row(j) for j in jobs], path=path)


def sync_tracker_rows_to_sheets(rows: list[dict[str, Any]], *, dry_run: bool = False) -> dict[str, Any]:
    """Upsert local CSV; Google Sheets API optional when credentials are set."""
    settings = get_settings()
    creds_path = (getattr(settings, "google_sheets_credentials_json", None) or "").strip()
    spreadsheet_id = (getattr(settings, "google_sheets_spreadsheet_id", None) or "").strip()

    if dry_run:
        return {"ok": True, "synced": len(rows), "destination": "dry_run"}

    csv_path = upsert_tracker_rows_to_csv(rows)
    result: dict[str, Any] = {
        "ok": True,
        "synced": len(rows),
        "csv_path": str(csv_path),
    }

    if not creds_path or not spreadsheet_id:
        result["note"] = "Google Sheets not configured — rows upserted to CSV only"
        return result

    try:
        result["sheets"] = _upsert_tracker_rows_to_google_sheets(
            rows,
            credentials_path=Path(creds_path).expanduser(),
            spreadsheet_id=spreadsheet_id,
        )
    except Exception as exc:
        result["ok"] = False
        result["sheets_error"] = str(exc)
    return result


def sync_jobs_to_sheets(jobs: list[Job], *, dry_run: bool = False) -> dict[str, Any]:
    rows = [job_to_tracker_row(job) for job in jobs]
    return sync_tracker_rows_to_sheets(rows, dry_run=dry_run)


def _upsert_tracker_rows_to_google_sheets(
    rows: list[dict[str, Any]],
    *,
    credentials_path: Path,
    spreadsheet_id: str,
) -> dict[str, Any]:
    """Read sheet, merge by job_id/url, write back."""
    if not credentials_path.is_file():
        raise FileNotFoundError(f"Credentials not found: {credentials_path}")

    import httpx
    from google.auth.transport.requests import Request
    from google.oauth2 import service_account

    creds = service_account.Credentials.from_service_account_file(
        str(credentials_path),
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    creds.refresh(Request())
    token = creds.token
    if not token:
        raise RuntimeError("Failed to obtain Google access token")

    headers = {"Authorization": f"Bearer {token}"}
    base = f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values/Sheet1"

    with httpx.Client(timeout=30.0) as client:
        resp = client.get(f"{base}!A1:Z", headers=headers)
        existing_rows: list[dict[str, Any]] = []
        if resp.status_code < 400:
            values = resp.json().get("values") or []
            if values:
                header = values[0]
                for line in values[1:]:
                    row = {header[i]: (line[i] if i < len(line) else "") for i in range(len(header))}
                    existing_rows.append(row)

        merged: dict[str, dict[str, Any]] = {}
        for row in existing_rows:
            merged[_row_key(row)] = row
        for row in rows:
            normalized = {k: row.get(k, "") for k in _FIELDNAMES}
            merged[_row_key(normalized)] = normalized

        out_values = [_FIELDNAMES]
        for row in merged.values():
            out_values.append([row.get(f) or "" for f in _FIELDNAMES])

        write = client.put(
            f"{base}!A1",
            headers=headers,
            json={"values": out_values},
        )
        if write.status_code >= 400:
            raise RuntimeError(f"Sheets API {write.status_code}: {write.text[:300]}")

    return {"upserted": len(rows), "total_rows": len(merged), "spreadsheet_id": spreadsheet_id}
