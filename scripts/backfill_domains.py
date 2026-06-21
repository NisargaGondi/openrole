#!/usr/bin/env python3
"""Backfill missing company domains using domain_resolver."""

from __future__ import annotations

import argparse
import json
import sys

from sqlalchemy import or_, select

from openrole.db.models import Company
from openrole.db.session import init_db, session_scope
from openrole.tools.domain_resolver import resolve_company_domain


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill null company domains")
    parser.add_argument("--dry-run", action="store_true", help="Print only; do not write")
    args = parser.parse_args()

    init_db()
    updated: list[dict] = []
    skipped: list[str] = []

    with session_scope() as session:
        companies = session.scalars(
            select(Company).where(or_(Company.domain.is_(None), Company.domain == ""))
        ).all()
        for company in companies:
            resolution = resolve_company_domain(company_name=company.name)
            if resolution is None:
                skipped.append(company.name)
                continue
            entry = {
                "company": company.name,
                "domain": resolution.domain,
                "source": resolution.source,
                "confidence": resolution.confidence,
            }
            updated.append(entry)
            if not args.dry_run:
                company.domain = resolution.domain

    print(json.dumps({"updated": updated, "skipped": skipped}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
