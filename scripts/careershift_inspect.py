#!/usr/bin/env python3
"""Dump CareerShift contacts search field selectors (debug UI changes).

Verified UI map (app.careershift.com/contacts/search):
  - Name:            input[placeholder="Name"]
  - School Attended: input[placeholder="School Attended"]
  - Company:         click [class*="Combobox"]:has-text("Search by company name")
                     then fill input[role="combobox"][data-active-item="true"]
  - Search:          button "Search" (exact)
  - Results API:     GET /api/v2/contacts/search?...companyId[]=...
  - Result cards:    [class*="jobCard"][role="button"]
"""

from __future__ import annotations

import asyncio
import json
import sys


async def _run() -> int:
    from patchright.async_api import async_playwright

    from openrole.scrapers.careershift_auth import CONTACTS_SEARCH_URL, session_is_ready
    from openrole.scrapers.careershift_client import PROFILE_DIR, _main_search_fields

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as playwright:
        context = await playwright.chromium.launch_persistent_context(
            str(PROFILE_DIR),
            headless=False,
            viewport={"width": 1280, "height": 900},
        )
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto(CONTACTS_SEARCH_URL, wait_until="domcontentloaded", timeout=60_000)
        try:
            await page.wait_for_load_state("networkidle", timeout=25_000)
        except Exception:
            pass

        print(f"URL: {page.url}")
        print(f"Session ready: {await session_is_ready(page)}")

        fields, count = await _main_search_fields(page)
        print(f"Main search fields found: {count}")

        for idx in range(min(count, 6)):
            el = fields.nth(idx)
            meta = await el.evaluate(
                """(node) => ({
                    tag: node.tagName,
                    type: node.getAttribute('type'),
                    role: node.getAttribute('role'),
                    placeholder: node.getAttribute('placeholder'),
                    ariaLabel: node.getAttribute('aria-label'),
                    className: node.className,
                })"""
            )
            print(f"\n--- field {idx} ---")
            print(json.dumps(meta, indent=2))

        combo_count = await page.locator('[class*="Combobox"]').count()
        print(f"\nCombobox wrappers: {combo_count}")

        await context.close()
    return 0


def main() -> None:
    try:
        raise SystemExit(asyncio.run(_run()))
    except ImportError:
        print("Run: bash scripts/install_careershift.sh", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
