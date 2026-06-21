#!/usr/bin/env python3
"""Handshake login — keeps Chrome open until CMU SSO + Cloudflare complete."""

from __future__ import annotations

import argparse
import sys

from openrole.integrations.browser_login import run_handshake_login


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Log in to Handshake (CMU) and save local session.")
    parser.add_argument("--force", action="store_true", help="Always open login flow.")
    parser.add_argument("--clear-profile", action="store_true", help="Delete saved profile first.")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    ok, msg = run_handshake_login(force=True, clear_profile=args.clear_profile)
    print(msg)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
