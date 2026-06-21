#!/usr/bin/env python3
"""Delete all jobs from the local database (fresh testing reset)."""

from __future__ import annotations

import argparse
import json
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="Delete all jobs, outreach, and applications")
    parser.add_argument("--yes", action="store_true", help="Skip confirmation prompt")
    args = parser.parse_args()

    if not args.yes:
        print("This removes ALL jobs. Re-run with --yes to confirm.")
        return 1

    from openrole.db.repository import delete_all_jobs
    from openrole.db.session import init_db, session_scope

    init_db()
    with session_scope() as session:
        counts = delete_all_jobs(session)
    print(json.dumps(counts, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
