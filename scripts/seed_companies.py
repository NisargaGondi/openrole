#!/usr/bin/env python3
"""Seed company metadata for ATS/careers discovery (scout targets)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from openrole.db.seed_companies import seed_companies_from_file


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed scout target companies into DB")
    parser.add_argument(
        "file",
        nargs="?",
        default="data/scout_targets.yaml",
        help="YAML/JSON file with company targets",
    )
    args = parser.parse_args()

    try:
        result = seed_companies_from_file(args.file)
    except (FileNotFoundError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
