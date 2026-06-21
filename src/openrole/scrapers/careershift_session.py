"""Persistent CareerShift Chromium session (shared by one-shot runs and the daemon)."""

from __future__ import annotations

import asyncio
from typing import Any

from openrole.scrapers.careershift_client import (
    PROFILE_DIR,
    CareerShiftSessionError,
    _BatchBudget,
    _MAX_DETAIL_PER_QUERY,
    _batch_timeout_s,
    _capture_json_response,
    _dedupe_contacts,
    _enrich_contacts_from_detail_panels,
    _fill_contact_search,
    _page_has_no_results,
    _parse_results_from_dom,
    _reset_search_page,
    _skip_detail_enrichment,
    _soft_reset_between_queries,
    _wait_for_results,
    to_ranking_person,
)
from openrole.scrapers.careershift_auth import session_is_ready


class CareerShiftBrowserSession:
    """One Playwright persistent context — reuse across multiple search batches."""

    def __init__(self) -> None:
        self._playwright: Any = None
        self._context: Any = None
        self._page: Any = None
        self._captured: list[dict[str, Any]] = []
        self._active_company: dict[str, str] = {"name": ""}
        self._response_handler_attached = False

    @property
    def page(self) -> Any:
        return self._page

    async def start(self, *, headless: bool) -> None:
        from patchright.async_api import async_playwright

        PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        self._playwright = await async_playwright().start()
        self._context = await self._playwright.chromium.launch_persistent_context(
            str(PROFILE_DIR),
            headless=headless,
            viewport={"width": 1280, "height": 900},
        )
        self._page = self._context.pages[0] if self._context.pages else await self._context.new_page()
        self._attach_response_handler()
        await _reset_search_page(self._page)
        if not await session_is_ready(self._page):
            raise CareerShiftSessionError(
                "CareerShift session expired or not logged in. "
                "Re-login: python scripts/careershift_login.py --clear-profile --force"
            )

    def _attach_response_handler(self) -> None:
        if self._response_handler_attached or self._page is None:
            return

        page = self._page
        captured = self._captured
        active_company = self._active_company

        def _on_response(response) -> None:
            if "careershift.com" not in response.url.lower():
                return
            if response.request.resource_type not in ("xhr", "fetch"):
                return
            ct = (response.headers.get("content-type") or "").lower()
            if "json" not in ct:
                return
            asyncio.create_task(
                _capture_json_response(
                    response,
                    captured,
                    company_name=active_company["name"],
                )
            )

        page.on("response", _on_response)
        self._response_handler_attached = True

    async def search_batch(self, queries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not self._page:
            raise CareerShiftSessionError("CareerShift browser session not started")
        return await execute_contact_search_batch(
            self._page,
            queries,
            captured=self._captured,
            active_company=self._active_company,
            budget=_BatchBudget(_batch_timeout_s()),
        )

    async def session_ok(self) -> bool:
        if not self._page:
            return False
        try:
            return await session_is_ready(self._page)
        except Exception:
            return False

    async def close(self) -> None:
        if self._context:
            try:
                await self._context.close()
            except Exception:
                pass
            self._context = None
        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception:
                pass
            self._playwright = None
        self._page = None
        self._response_handler_attached = False


async def execute_contact_search_batch(
    page,
    queries: list[dict[str, Any]],
    *,
    captured: list[dict[str, Any]],
    active_company: dict[str, str],
    budget: _BatchBudget,
) -> list[dict[str, Any]]:
    """Run CareerShift contact queries on an already-open search page."""
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    timed_out = False

    for query_idx, query in enumerate(queries):
        if budget.expired:
            timed_out = True
            break
        if query_idx > 0:
            await _soft_reset_between_queries(page)

        captured.clear()
        active_company["name"] = str(query["company_name"])
        await _fill_contact_search(
            page,
            company_name=active_company["name"],
            school_name=query.get("school_name"),
            location=query.get("location"),
            position_keywords=query.get("position_keywords"),
        )
        await _wait_for_results(page, company_name=active_company["name"])

        if await _page_has_no_results(page):
            continue

        parsed = _dedupe_contacts(captured)
        if not parsed:
            parsed = await _parse_results_from_dom(page, max_results=int(query.get("max_results") or 15))

        max_detail = 0
        if query.get("force_detail"):
            max_detail = min(int(query.get("max_detail") or 1), _MAX_DETAIL_PER_QUERY)
        elif not query.get("skip_detail", _skip_detail_enrichment()):
            max_detail = min(int(query.get("max_results") or 15), _MAX_DETAIL_PER_QUERY)
        if max_detail > 0:
            parsed = await _enrich_contacts_from_detail_panels(
                page,
                parsed,
                max_detail=max_detail,
                budget=budget,
            )

        max_results = int(query.get("max_results") or 15)
        for row in parsed[:max_results]:
            if budget.expired:
                timed_out = True
                break
            person = to_ranking_person(row)
            pid = str(person.get("id") or "")
            if pid and pid in seen:
                continue
            if pid:
                seen.add(pid)
            merged.append(person)
        if timed_out:
            break

    return merged
