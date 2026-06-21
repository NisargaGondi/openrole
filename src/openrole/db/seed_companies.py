"""Seed scout target companies from YAML/JSON into the database."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlalchemy import select

from openrole.db.models import Company
from openrole.db.session import session_scope


def load_company_targets(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    if path.suffix in (".yaml", ".yml"):
        try:
            import yaml
        except ImportError as exc:
            raise RuntimeError("Install PyYAML or use a .json targets file") from exc
        raw = yaml.safe_load(text) or {}
    else:
        raw = json.loads(text)
    return list(raw.get("companies") or [])


def seed_companies_from_file(path: Path | str) -> dict[str, Any]:
    """Upsert companies from a scout targets file. Returns summary dict."""
    target = Path(path)
    if not target.is_file():
        raise FileNotFoundError(f"Targets file not found: {target}")

    companies = load_company_targets(target)
    if not companies:
        raise ValueError("No companies in targets file")

    upserted = 0
    scout_metadata = 0
    with session_scope() as session:
        for item in companies:
            name = item.get("name")
            if not name:
                continue
            domain = item.get("domain")
            meta = {k: v for k, v in item.items() if k not in ("name", "domain")}
            existing = None
            if domain:
                existing = session.scalar(
                    select(Company).where(Company.domain == domain).limit(1)
                )
            if existing is None:
                existing = session.scalar(
                    select(Company).where(Company.name == name).limit(1)
                )
            if existing is None:
                existing = Company(name=name, domain=domain, metadata_json=meta)
                session.add(existing)
            else:
                existing.name = name
                if domain:
                    existing.domain = domain
                merged = dict(existing.metadata_json or {})
                merged.update(meta)
                existing.metadata_json = merged
            session.flush()
            upserted += 1
            if _has_scout_metadata(meta):
                scout_metadata += 1

    return {
        "upserted": upserted,
        "with_scout_metadata": scout_metadata,
        "file": str(target),
    }


def count_scout_target_companies() -> dict[str, int]:
    """Count companies in DB that have ATS/careers metadata for scout."""
    from openrole.agents.scout_rotation import is_junk_scout_company

    with session_scope() as session:
        companies = [
            c
            for c in session.scalars(select(Company).order_by(Company.name.asc()))
            if not is_junk_scout_company(c)
        ]
    total = len(companies)
    with_meta = sum(1 for c in companies if _has_scout_metadata(c.metadata_json or {}))
    return {"total": total, "with_scout_metadata": with_meta}


def _has_scout_metadata(meta: dict[str, Any]) -> bool:
    keys = (
        "greenhouse_token",
        "greenhouse_board",
        "lever_slug",
        "lever_client",
        "ashby_org",
        "ashby_board",
        "careers_url",
    )
    return any(meta.get(k) for k in keys)
