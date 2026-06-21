#!/usr/bin/env python3
"""CareerShift login — keeps Chrome open until CMU member login completes."""

from __future__ import annotations

import argparse
import sys

from openrole.integrations.browser_login import run_careershift_login


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Log in to CareerShift (CMU) and save local session.")
    parser.add_argument("--force", action="store_true", help="Always open login flow.")
    parser.add_argument("--clear-profile", action="store_true", help="Delete saved profile first.")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    ok, msg = run_careershift_login(force=args.force, clear_profile=args.clear_profile)
    print(msg)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
