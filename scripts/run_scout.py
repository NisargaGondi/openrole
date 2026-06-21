#!/usr/bin/env python3
"""Run the Job Scout agent once (CLI)."""

from __future__ import annotations

import argparse
import json
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="OpenRole Job Scout — discover and score jobs")
    parser.add_argument(
        "--terms",
        nargs="+",
        help="Search terms (default: derived from selected resume)",
    )
    parser.add_argument(
        "--resume-label",
        default=None,
        help="Resume variant label (default: first in CANDIDATE_RESUME_PATHS)",
    )
    parser.add_argument("--location", default=None, help="JobSpy location (default: United States)")
    parser.add_argument("--min-score", type=int, default=None, help="Min relevance 0–100")
    parser.add_argument("--results", type=int, default=None, help="Results per search term")
    parser.add_argument("--no-ats", action="store_true", help="Skip ATS board discovery")
    parser.add_argument("--no-handshake", action="store_true", help="Skip Handshake search")
    parser.add_argument("--no-tavily", action="store_true", help="Skip Tavily ATS/careers discovery")
    parser.add_argument("--resume-analysis", action="store_true", help="Run resume optimizer on strong hits")
    parser.add_argument("--no-notion", action="store_true", help="Skip Notion sync")
    parser.add_argument("--no-sheets", action="store_true", help="Skip Sheets/CSV sync")
    parser.add_argument("--dry-run", action="store_true", help="Score only — do not persist")
    args = parser.parse_args()

    sites = ("indeed", "linkedin")

    from openrole.agents.job_scout import run_job_scout

    report = run_job_scout(
        resume_label=args.resume_label,
        search_terms=args.terms,
        location=args.location,
        sites=sites,
        min_score=args.min_score,
        results_per_term=args.results,
        include_ats_boards=not args.no_ats,
        include_handshake=not args.no_handshake,
        include_tavily=not args.no_tavily,
        run_resume_analysis=args.resume_analysis,
        sync_notion=not args.no_notion,
        sync_sheets=not args.no_sheets,
        dry_run=args.dry_run,
        trigger="manual",
    )
    print(json.dumps(report.to_dict(), indent=2))
    return 0 if not report.errors else 1


if __name__ == "__main__":
    sys.exit(main())
