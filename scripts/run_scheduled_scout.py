#!/usr/bin/env python3
"""Cron-friendly Job Scout — uses .env defaults + optional resume label."""

from __future__ import annotations

import argparse
import json
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Job Scout on a schedule (cron / launchd)")
    parser.add_argument(
        "--resume-label",
        default=None,
        help="Resume variant label (default: SCOUT_DEFAULT_RESUME_LABEL or first in .env)",
    )
    parser.add_argument("--min-score", type=int, default=None)
    parser.add_argument("--no-handshake", action="store_true")
    parser.add_argument("--no-sheets", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    from openrole.agents.job_scout import run_job_scout
    from openrole.config import get_settings

    settings = get_settings()
    resume_label = args.resume_label or settings.scout_default_resume_label or None

    report = run_job_scout(
        resume_label=resume_label,
        min_score=args.min_score,
        include_handshake=not args.no_handshake,
        sync_sheets=not args.no_sheets,
        dry_run=args.dry_run,
        trigger="scheduled",
    )
    print(json.dumps(report.to_dict(), indent=2))
    return 0 if not report.errors else 1


if __name__ == "__main__":
    sys.exit(main())
