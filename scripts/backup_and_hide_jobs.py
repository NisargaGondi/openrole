#!/usr/bin/env python3
"""Export all jobs/contacts/drafts to CSV, then hide jobs from UI (data kept in DB)."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from openrole.config import _REPO_ROOT
from openrole.db.models import Contact, Job, Outreach
from openrole.db.repository import list_contacts_for_job, list_jobs_for_tracker, list_outreach_drafts
from openrole.db.session import session_scope

BACKUP_ROOT = _REPO_ROOT / "data" / "backups"


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")


def main() -> None:
    stamp = _ts()
    out_dir = BACKUP_ROOT / stamp
    out_dir.mkdir(parents=True, exist_ok=True)

    with session_scope() as session:
        jobs = list_jobs_for_tracker(session, status="all", limit=5000, include_hidden=True)
        job_rows = []
        contact_rows = []
        draft_rows = []

        for job in jobs:
            company = job.company
            job_rows.append(
                {
                    "id": job.id,
                    "title": job.title,
                    "company": company.name if company else "",
                    "company_domain": company.domain if company else "",
                    "status": job.status.value,
                    "source_url": job.source_url or "",
                    "scout_score": (job.raw_payload or {}).get("scout", {}).get("relevance_score"),
                    "created_at": job.created_at.isoformat() if job.created_at else "",
                }
            )
            contacts = (
                list_contacts_for_job(session, company_id=job.company_id, source_job_id=job.id)
                if job.company_id
                else []
            )
            for c in contacts:
                contact_rows.append(
                    {
                        "id": c.id,
                        "job_id": job.id,
                        "full_name": c.full_name,
                        "title": c.title or "",
                        "email": c.email or "",
                        "linkedin_url": c.linkedin_url or "",
                        "has_research": bool(c.research_brief),
                        "tier": (c.metadata_json or {}).get("tier", ""),
                    }
                )
            drafts = list_outreach_drafts(session, job_id=job.id, limit=500)
            for d in drafts:
                c = session.get(Contact, d.contact_id) if d.contact_id else None
                draft_rows.append(
                    {
                        "id": d.id,
                        "job_id": job.id,
                        "contact_name": c.full_name if c else "",
                        "channel": d.channel.value if hasattr(d.channel, "value") else str(d.channel),
                        "subject": d.subject or "",
                        "body": d.body[:500],
                    }
                )

            payload = dict(job.raw_payload or {})
            payload["ui_hidden"] = True
            payload["ui_hidden_at"] = datetime.now(timezone.utc).isoformat()
            payload["backup_dir"] = str(out_dir.relative_to(_REPO_ROOT))
            job.raw_payload = payload
            from sqlalchemy.orm.attributes import flag_modified

            flag_modified(job, "raw_payload")

        for name, rows in [("jobs", job_rows), ("contacts", contact_rows), ("drafts", draft_rows)]:
            if not rows:
                continue
            path = out_dir / f"{name}.csv"
            with path.open("w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                w.writeheader()
                w.writerows(rows)

        manifest = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "jobs": len(job_rows),
            "contacts": len(contact_rows),
            "drafts": len(draft_rows),
            "note": "Jobs marked ui_hidden in DB — data not deleted",
        }
        (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(f"Backup written to {out_dir}")
    print(f"  jobs: {len(job_rows)} contacts: {len(contact_rows)} drafts: {len(draft_rows)}")
    print("All jobs marked ui_hidden — UI will show empty until you ingest/scout new roles.")


if __name__ == "__main__":
    main()
