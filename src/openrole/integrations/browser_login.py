"""Interactive Playwright logins for CareerShift and Handshake (CLI + Streamlit)."""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

CAREERSHIFT_PROFILE_DIR = Path.home() / ".openrole" / "careershift" / "profile"
HANDSHAKE_PROFILE_DIR = Path.home() / ".handshake-mcp" / "profile"
LOGIN_TIMEOUT_SEC = 600


def _clear_profile(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def _unlock_profile(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    for lock in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
        (path / lock).unlink(missing_ok=True)


async def careershift_interactive_login(*, force: bool = True, clear_profile: bool = False) -> tuple[bool, str]:
    from patchright.async_api import async_playwright

    from openrole.scrapers.careershift_auth import CONTACTS_SEARCH_URL, session_is_ready

    if clear_profile:
        _clear_profile(CAREERSHIFT_PROFILE_DIR)
    _unlock_profile(CAREERSHIFT_PROFILE_DIR)

    async with async_playwright() as playwright:
        context = await playwright.chromium.launch_persistent_context(
            str(CAREERSHIFT_PROFILE_DIR),
            headless=False,
            viewport={"width": 1280, "height": 720},
        )
        try:
            page = context.pages[0] if context.pages else await context.new_page()
            app_url = CONTACTS_SEARCH_URL

            if not force:
                await page.goto(app_url, wait_until="domcontentloaded", timeout=60_000)
                await asyncio.sleep(2)
                if await session_is_ready(page):
                    return True, f"Already logged in ({CAREERSHIFT_PROFILE_DIR})"

            await page.goto(app_url, wait_until="domcontentloaded", timeout=60_000)
            loop = asyncio.get_running_loop()
            deadline = loop.time() + LOGIN_TIMEOUT_SEC
            while loop.time() < deadline:
                if await session_is_ready(page):
                    await page.goto(app_url, wait_until="domcontentloaded", timeout=60_000)
                    await asyncio.sleep(2)
                    if await session_is_ready(page):
                        return True, f"CareerShift login saved to {CAREERSHIFT_PROFILE_DIR}"
                await asyncio.sleep(1)
            return False, "CareerShift login timed out — try again with clear profile"
        finally:
            await context.close()


async def handshake_interactive_login(*, force: bool = True, clear_profile: bool = False) -> tuple[bool, str]:
    from handshake_mcp_server.core.utils import wait_for_cf_challenge
    from patchright.async_api import async_playwright

    from openrole.scrapers.handshake_auth import session_is_ready

    if clear_profile:
        _clear_profile(HANDSHAKE_PROFILE_DIR)
    _unlock_profile(HANDSHAKE_PROFILE_DIR)

    base_url = "https://app.joinhandshake.com"

    async with async_playwright() as playwright:
        context = await playwright.chromium.launch_persistent_context(
            str(HANDSHAKE_PROFILE_DIR),
            headless=False,
            viewport={"width": 1280, "height": 720},
        )
        try:
            page = context.pages[0] if context.pages else await context.new_page()

            if not force:
                await page.goto(f"{base_url}/stu", wait_until="domcontentloaded", timeout=60_000)
                await wait_for_cf_challenge(page, timeout=90_000)
                await asyncio.sleep(2)
                if await session_is_ready(page):
                    return True, f"Already logged in ({HANDSHAKE_PROFILE_DIR})"

            await page.goto(f"{base_url}/login", wait_until="domcontentloaded", timeout=60_000)
            loop = asyncio.get_running_loop()
            deadline = loop.time() + LOGIN_TIMEOUT_SEC
            while loop.time() < deadline:
                await wait_for_cf_challenge(page, timeout=90_000)
                if await session_is_ready(page):
                    await page.goto(f"{base_url}/stu", wait_until="domcontentloaded", timeout=60_000)
                    await wait_for_cf_challenge(page, timeout=90_000)
                    await asyncio.sleep(2)
                    if await session_is_ready(page):
                        return True, f"Handshake login saved to {HANDSHAKE_PROFILE_DIR}"
                await asyncio.sleep(1)
            return False, "Handshake login timed out — try again with clear profile"
        finally:
            await context.close()


def run_careershift_login(*, force: bool = True, clear_profile: bool = False) -> tuple[bool, str]:
    try:
        return asyncio.run(careershift_interactive_login(force=force, clear_profile=clear_profile))
    except ImportError:
        return False, "Install CareerShift extras: bash scripts/install_careershift.sh"
    except Exception as exc:
        return False, str(exc)


def run_handshake_login(*, force: bool = True, clear_profile: bool = False) -> tuple[bool, str]:
    try:
        return asyncio.run(handshake_interactive_login(force=force, clear_profile=clear_profile))
    except ImportError:
        return False, "Install Handshake extras: bash scripts/install_handshake.sh"
    except Exception as exc:
        return False, str(exc)
