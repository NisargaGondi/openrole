#!/usr/bin/env python3
"""Handshake login — keeps Chrome open until CMU SSO + Cloudflare fully complete.

Upstream `is_logged_in()` false-positives on Cloudflare "Just a moment..." pages
and `/access?access_state_id=...` redirects, which closes the browser immediately.
"""

from __future__ import annotations

import argparse
import asyncio
import shutil
import sys
from pathlib import Path

PROFILE_DIR = Path.home() / ".handshake-mcp" / "profile"
BASE_URL = "https://app.joinhandshake.com"
LOGIN_TIMEOUT_SEC = 600


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Log in to Handshake (CMU) and save local session.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Always open the login page (skip 'already logged in' short-circuit).",
    )
    parser.add_argument(
        "--clear-profile",
        action="store_true",
        help="Delete ~/.handshake-mcp/profile before login (use if prior login was a false positive).",
    )
    return parser.parse_args()


def _clear_profile() -> None:
    if PROFILE_DIR.exists():
        shutil.rmtree(PROFILE_DIR)
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Cleared profile at {PROFILE_DIR}")


async def _run_login(*, force: bool) -> int:
    from handshake_mcp_server.core.utils import wait_for_cf_challenge
    from patchright.async_api import async_playwright

    from openrole.scrapers.handshake_auth import session_is_ready

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    for lock in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
        (PROFILE_DIR / lock).unlink(missing_ok=True)

    async with async_playwright() as playwright:
        context = await playwright.chromium.launch_persistent_context(
            str(PROFILE_DIR),
            headless=False,
            viewport={"width": 1280, "height": 720},
        )
        try:
            page = context.pages[0] if context.pages else await context.new_page()

            if not force:
                await page.goto(
                    f"{BASE_URL}/stu",
                    wait_until="domcontentloaded",
                    timeout=60_000,
                )
                await wait_for_cf_challenge(page, timeout=90_000)
                await asyncio.sleep(2)
                if await session_is_ready(page):
                    print(f"Already logged in. Profile: {PROFILE_DIR}")
                    print("(Use --force to re-login anyway.)")
                    return 0

            print(f"Opening {BASE_URL}/login")
            print("Complete CMU SSO in the Chrome window — it will stay open until login finishes.")
            print(f"Waiting up to {LOGIN_TIMEOUT_SEC // 60} minutes…")
            await page.goto(
                f"{BASE_URL}/login",
                wait_until="domcontentloaded",
                timeout=60_000,
            )

            loop = asyncio.get_running_loop()
            deadline = loop.time() + LOGIN_TIMEOUT_SEC
            last_url = ""
            while loop.time() < deadline:
                await wait_for_cf_challenge(page, timeout=90_000)
                current = page.url
                if current != last_url:
                    print(f"  … {current}")
                    last_url = current

                if await session_is_ready(page):
                    await page.goto(
                        f"{BASE_URL}/stu",
                        wait_until="domcontentloaded",
                        timeout=60_000,
                    )
                    await wait_for_cf_challenge(page, timeout=90_000)
                    await asyncio.sleep(2)
                    if await session_is_ready(page):
                        print(f"Login successful! Profile saved to: {PROFILE_DIR}")
                        return 0

                await asyncio.sleep(1)

            print("Login timed out. Try: python scripts/handshake_login.py --clear-profile --force")
            return 1
        finally:
            await context.close()


def main() -> None:
    args = _parse_args()
    if args.clear_profile:
        _clear_profile()

    code = 1
    try:
        code = asyncio.run(_run_login(force=args.force))
    except ImportError:
        print(
            "Handshake extras missing. Run: bash scripts/install_handshake.sh",
            file=sys.stderr,
        )
    except KeyboardInterrupt:
        print("\nLogin cancelled.")
    except Exception as exc:
        name = type(exc).__name__
        if "Timeout" in name:
            print(f"Browser navigation failed: {exc}")
        else:
            print(f"Login failed: {exc}", file=sys.stderr)
    sys.exit(code)


if __name__ == "__main__":
    main()
