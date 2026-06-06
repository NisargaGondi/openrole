#!/usr/bin/env python3
"""CareerShift login — keeps Chrome open until CMU member login completes.

Use your CareerShift account (typically your @andrew.cmu.edu email + password).
Sign up once with group code CMU if needed:
  https://www.careershift.com/user/signup?group=CMU

App URL after login: https://app.careershift.com/contacts/search
"""

from __future__ import annotations

import argparse
import asyncio
import shutil
import sys
from pathlib import Path

from openrole.scrapers.careershift_auth import CONTACTS_SEARCH_URL

PROFILE_DIR = Path.home() / ".openrole" / "careershift" / "profile"
APP_HOME_URL = CONTACTS_SEARCH_URL
LOGIN_TIMEOUT_SEC = 600


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Log in to CareerShift (CMU) and save local session.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Always open the login page (skip 'already logged in' short-circuit).",
    )
    parser.add_argument(
        "--clear-profile",
        action="store_true",
        help="Delete ~/.openrole/careershift/profile before login.",
    )
    return parser.parse_args()


def _clear_profile() -> None:
    if PROFILE_DIR.exists():
        shutil.rmtree(PROFILE_DIR)
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Cleared profile at {PROFILE_DIR}")


async def _run_login(*, force: bool) -> int:
    from patchright.async_api import async_playwright

    from openrole.scrapers.careershift_auth import session_is_ready

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
                    APP_HOME_URL,
                    wait_until="domcontentloaded",
                    timeout=60_000,
                )
                await asyncio.sleep(2)
                if await session_is_ready(page):
                    print(f"Already logged in. Profile: {PROFILE_DIR}")
                    print("(Use --force to re-login anyway.)")
                    return 0

            print(f"Opening {APP_HOME_URL}")
            print("Sign in with your CareerShift email + password if prompted.")
            print("CMU students: use @andrew.cmu.edu (group code CMU at signup if new).")
            print(f"Waiting up to {LOGIN_TIMEOUT_SEC // 60} minutes for /contacts/search…")
            await page.goto(
                APP_HOME_URL,
                wait_until="domcontentloaded",
                timeout=60_000,
            )

            loop = asyncio.get_running_loop()
            deadline = loop.time() + LOGIN_TIMEOUT_SEC
            last_url = ""
            while loop.time() < deadline:
                current = page.url
                if current != last_url:
                    print(f"  … {current}")
                    last_url = current

                if await session_is_ready(page):
                    await page.goto(
                        APP_HOME_URL,
                        wait_until="domcontentloaded",
                        timeout=60_000,
                    )
                    await asyncio.sleep(2)
                    if await session_is_ready(page):
                        print(f"Login successful! Profile saved to: {PROFILE_DIR}")
                        return 0

                await asyncio.sleep(1)

            print("Login timed out. Try: python scripts/careershift_login.py --clear-profile --force")
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
            "CareerShift extras missing. Run: bash scripts/install_careershift.sh",
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
