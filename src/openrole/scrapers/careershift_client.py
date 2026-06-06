"""CareerShift contact search via local Playwright session (CMU member login).

Security model mirrors Handshake:
- Browser profile at ~/.openrole/careershift/profile (local cookies only).
- No credentials stored in OpenRole code or .env.
- Run `python scripts/careershift_login.py` once to save your session.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from openrole.scrapers.careershift_auth import (
    APP_LOGIN_URL,
    CMU_SIGNUP_URL,
    CONTACTS_SEARCH_URL,
)
from openrole.scrapers.handshake_client import patchright_browser_ready

PROFILE_DIR = Path.home() / ".openrole" / "careershift" / "profile"

# app.careershift.com contacts search UI (verified via scripts/careershift_inspect.py)
_CONTACTS_API_PATH = "/api/v2/contacts/search"
_COMPANY_COMBO_INPUT = 'input[role="combobox"][data-active-item="true"]'
_RESULT_CARD = '[class*="jobCard"][role="button"]'

_PATCHRIGHT_HINT = (
    "Patchright Chromium is missing. Run once:\n"
    "  bash scripts/install_careershift.sh\n"
    "or: python -m patchright install chromium"
)

_LOGIN_HINT = (
    "No CareerShift login profile found. Run once:\n"
    "  python scripts/careershift_login.py --clear-profile --force\n"
    "Session stays in ~/.openrole/careershift/profile on your machine only."
)


class CareerShiftNotConfiguredError(RuntimeError):
    pass


class CareerShiftSessionError(RuntimeError):
    pass


class CareerShiftSearchError(RuntimeError):
    pass


def patchright_installed() -> bool:
    try:
        import patchright  # noqa: F401

        return True
    except ImportError:
        return False


def profile_ready() -> bool:
    return PROFILE_DIR.exists() and any(PROFILE_DIR.iterdir())


def is_ready() -> bool:
    return patchright_installed() and patchright_browser_ready() and profile_ready()


def _headless() -> bool:
    env = os.environ.get("OPENROLE_CAREERSHIFT_HEADLESS")
    if env is not None:
        return env.lower() in ("1", "true", "yes")
    return sys.platform != "darwin"


def search_contacts(
    *,
    company_name: str,
    location: str | None = None,
    position_keywords: list[str] | None = None,
    school_name: str | None = None,
    max_results: int = 25,
) -> list[dict[str, Any]]:
    """Search CareerShift contacts; returns Apollo-shaped person dicts."""
    results = search_contacts_batch(
        [
            {
                "company_name": company_name,
                "location": location,
                "position_keywords": position_keywords,
                "school_name": school_name,
                "max_results": max_results,
            }
        ]
    )
    return results


def search_contacts_batch(queries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Run multiple CareerShift searches in one browser session."""
    if not queries:
        return []
    if not patchright_installed():
        raise CareerShiftNotConfiguredError(
            "Install CareerShift support: pip install 'openrole[careershift]'"
        )
    if not patchright_browser_ready():
        raise CareerShiftNotConfiguredError(_PATCHRIGHT_HINT)
    if not profile_ready():
        raise CareerShiftNotConfiguredError(_LOGIN_HINT)

    try:
        return asyncio.run(_search_contacts_batch_async(queries))
    except (CareerShiftSessionError, CareerShiftSearchError):
        raise
    except Exception as exc:
        raise CareerShiftSearchError(
            f"CareerShift browser automation failed: {type(exc).__name__}: {exc}"
        ) from exc


def probe_careershift(*, company_name: str = "Google") -> dict[str, Any]:
    """Connectivity test for Settings diagnostics."""
    if not is_ready():
        missing = []
        if not patchright_installed():
            missing.append("patchright not installed")
        if not patchright_browser_ready():
            missing.append("Chromium missing")
        if not profile_ready():
            missing.append("not logged in")
        return {"ok": False, "error": "; ".join(missing) or "CareerShift not ready"}
    try:
        rows = search_contacts(
            company_name=company_name,
            max_results=3,
        )
        sample = None
        if rows:
            fields = person_to_fields(rows[0])
            sample = {
                "name": fields.get("full_name"),
                "title": fields.get("title"),
                "email": fields.get("email"),
                "location": fields.get("location"),
            }
        return {"ok": True, "count": len(rows), "company": company_name, "sample": sample}
    except (CareerShiftSessionError, CareerShiftSearchError) as exc:
        return {"ok": False, "error": str(exc)}
    except Exception as exc:
        return {"ok": False, "error": f"CareerShift probe failed: {type(exc).__name__}: {exc}"}


def person_to_fields(person: dict[str, Any]) -> dict[str, Any]:
    """Normalize CareerShift / merged person dict to common OpenRole fields."""
    loc_parts = [
        person.get("city"),
        person.get("state"),
        person.get("country"),
    ]
    location = person.get("location") or ", ".join(p for p in loc_parts if p) or None
    cs_id = person.get("careershift_id") or person.get("id")
    if isinstance(cs_id, str) and cs_id.startswith("cs:"):
        cs_id = cs_id[3:]
    return {
        "full_name": _display_name(person),
        "title": person.get("title"),
        "email": person.get("email"),
        "linkedin_url": person.get("linkedin_url") or person.get("linkedInUrl"),
        "location": location,
        "apollo_person_id": person.get("apollo_person_id"),
        "careershift_id": cs_id,
        "has_email": bool(person.get("email") or person.get("has_email")),
        "organization_name": person.get("company") or person.get("organization_name"),
        "raw": person,
    }


def to_ranking_person(contact: dict[str, Any]) -> dict[str, Any]:
    """Convert parsed CareerShift contact to dict compatible with people ranking."""
    cs_id = contact.get("careershift_id") or contact.get("id") or _stable_id(contact)
    first, last = _split_name(contact.get("full_name") or contact.get("name") or "")
    return {
        "id": f"cs:{cs_id}",
        "careershift_id": cs_id,
        "first_name": first,
        "last_name": last,
        "name": contact.get("full_name") or contact.get("name"),
        "title": contact.get("title"),
        "email": contact.get("email"),
        "linkedin_url": contact.get("linkedin_url"),
        "city": _city_from_location(contact.get("location")),
        "state": _state_from_location(contact.get("location")),
        "location": contact.get("location"),
        "has_email": bool(contact.get("email") or contact.get("has_email")),
        "company": contact.get("company"),
        "school": contact.get("school"),
        "_openrole_careershift": True,
    }


async def _search_contacts_batch_async(queries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from patchright.async_api import async_playwright

    from openrole.scrapers.careershift_auth import session_is_ready

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()

    async with async_playwright() as playwright:
        context = await playwright.chromium.launch_persistent_context(
            str(PROFILE_DIR),
            headless=_headless(),
            viewport={"width": 1280, "height": 900},
        )
        try:
            page = context.pages[0] if context.pages else await context.new_page()
            captured: list[dict[str, Any]] = []
            active_company: dict[str, str] = {"name": ""}

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

            await _reset_search_page(page)

            if not await session_is_ready(page):
                raise CareerShiftSessionError(
                    "CareerShift session expired or not logged in. "
                    "Re-login: python scripts/careershift_login.py --clear-profile --force"
                )

            for query_idx, query in enumerate(queries):
                if query_idx > 0:
                    await _reset_search_page(page)

                captured.clear()
                active_company["name"] = str(query["company_name"])
                await _fill_contact_search(
                    page,
                    company_name=active_company["name"],
                    school_name=query.get("school_name"),
                )
                await _wait_for_results(page, company_name=active_company["name"])

                if await _page_has_no_results(page):
                    continue

                parsed = _dedupe_contacts(captured)
                if not parsed:
                    parsed = await _parse_results_from_dom(
                        page, max_results=int(query.get("max_results") or 25)
                    )

                parsed = await _enrich_contacts_from_detail_panels(
                    page,
                    parsed,
                    max_detail=min(int(query.get("max_results") or 25), 15),
                )

                max_results = int(query.get("max_results") or 25)
                for row in parsed[:max_results]:
                    person = to_ranking_person(row)
                    pid = str(person.get("id") or "")
                    if pid and pid in seen:
                        continue
                    if pid:
                        seen.add(pid)
                    merged.append(person)
        finally:
            await context.close()

    return merged


async def _search_contacts_async(
    *,
    company_name: str,
    location: str | None,
    position_keywords: list[str] | None,
    school_name: str | None,
    max_results: int,
) -> list[dict[str, Any]]:
    return await _search_contacts_batch_async(
        [
            {
                "company_name": company_name,
                "location": location,
                "position_keywords": position_keywords,
                "school_name": school_name,
                "max_results": max_results,
            }
        ]
    )


async def _capture_json_response(
    response,
    sink: list[dict[str, Any]],
    *,
    company_name: str = "",
) -> None:
    try:
        if response.status >= 400:
            return
        data = await response.json()
    except Exception:
        return

    url = response.url.lower()
    if _CONTACTS_API_PATH in url and isinstance(data, dict):
        results = data.get("results")
        if not isinstance(results, list):
            return
        # Ignore CMU default Pennsylvania feed; keep company-filtered searches.
        if "companyid" not in url and company_name:
            if "state=pa" in url or "locationstate=pennsylvania" in url:
                return
        for row in results:
            if isinstance(row, dict):
                sink.append(_normalize_api_contact(row))
        return

    for row in _extract_contacts_from_json(data):
        sink.append(row)


async def _fill_contact_search(
    page,
    *,
    company_name: str,
    school_name: str | None = None,
    location: str | None = None,
    position_keywords: list[str] | None = None,
) -> None:
    """Fill contacts search — company (+ optional school) only.

    Location/title filters are applied in OpenRole ranking, not CareerShift UI.
    Combining many job titles in CareerShift often returns zero results.
    """
    _ = location, position_keywords
    await _ensure_contacts_search_ready(page)
    await _clear_search_fields(page)

    if school_name:
        school = page.get_by_placeholder("School Attended").first
        if await school.count() > 0:
            await _type_into_field(school, school_name)

    await _fill_company_combobox(page, company_name)
    await _click_search(page)


async def _fill_company_combobox(page, company_name: str) -> None:
    """Company picker: combobox wrapper in search bar + hidden role=combobox input."""
    for attempt in range(2):
        try:
            await _fill_company_combobox_once(page, company_name)
            return
        except Exception:
            if attempt == 0:
                await _reset_search_page(page)
                continue
            raise


async def _fill_company_combobox_once(page, company_name: str) -> None:
    """Company picker: combobox wrapper in search bar + hidden role=combobox input."""
    search_btn = page.get_by_role("button", name="Search", exact=True)
    bar = search_btn.locator('xpath=ancestor::*[.//input][1]')

    wrapper = bar.locator('[class*="ComboboxInputWrapper"]').last
    if await wrapper.count() > 0:
        await wrapper.click(timeout=8_000)
    else:
        trigger = page.locator('[class*="Combobox"]').filter(
            has_text=re.compile(r"search by company", re.I)
        ).first
        await trigger.click(timeout=8_000)

    combo_input = page.locator(_COMPANY_COMBO_INPUT).first
    if await combo_input.count() == 0:
        combo_input = bar.locator('input[role="combobox"]').last
    await combo_input.wait_for(state="attached", timeout=8_000)
    await combo_input.fill(company_name)
    await asyncio.sleep(0.9)

    await _select_company_option(page, company_name)


async def _locate_company_trigger(page):
    """Legacy helper — prefer _fill_company_combobox."""
    search_btn = page.get_by_role("button", name="Search", exact=True)
    bar = search_btn.locator('xpath=ancestor::*[.//input][1]')
    wrapper = bar.locator('[class*="ComboboxInputWrapper"]').last
    if await wrapper.count() > 0:
        return wrapper
    return page.get_by_text("Search by company name", exact=False).first


async def _reset_search_page(page) -> None:
    await page.goto(CONTACTS_SEARCH_URL, wait_until="domcontentloaded", timeout=60_000)
    try:
        await page.wait_for_load_state("networkidle", timeout=20_000)
    except Exception:
        pass
    await _ensure_contacts_search_ready(page)


async def _select_company_option(page, company_name: str) -> None:
    options = page.get_by_role("option")
    count = await options.count()
    if count == 0:
        await page.keyboard.press("Enter")
        return

    tokens = [t for t in re.sub(r"[^a-z0-9]+", " ", company_name.lower()).split() if len(t) > 2]
    best_idx = -1
    best_score = -1
    for idx in range(count):
        text = (await options.nth(idx).inner_text()).strip()
        if text.lower().startswith("contains"):
            continue
        text_l = text.lower()
        score = sum(1 for t in tokens if t in text_l)
        if company_name.lower() in text_l:
            score += 3
        if score > best_score:
            best_score = score
            best_idx = idx

    if best_idx >= 0 and best_score > 0:
        await options.nth(best_idx).click()
        return

    for label in (company_name, f"{company_name} Inc"):
        opt = page.get_by_role("option", name=label, exact=True)
        if await opt.count() > 0:
            await opt.first.click()
            return

    await options.first.click()


async def _enrich_contacts_from_detail_panels(
    page,
    contacts: list[dict[str, Any]],
    *,
    max_detail: int = 12,
) -> list[dict[str, Any]]:
    """Click result cards and View contact details to unblur email/phone/location."""
    if not contacts:
        return contacts

    cards = page.locator(_RESULT_CARD)
    card_count = await cards.count()
    enriched = list(contacts)
    seen_names = {c.get("full_name", "").lower() for c in enriched}

    for idx in range(min(card_count, max_detail)):
        try:
            await cards.nth(idx).click(timeout=5_000)
            await asyncio.sleep(0.45)
            for pattern in (
                re.compile(r"view contact details", re.I),
                re.compile(r"contact details", re.I),
                re.compile(r"view details", re.I),
            ):
                btn = page.get_by_role("button", name=pattern)
                if await btn.count() > 0:
                    await btn.first.click(timeout=5_000)
                    await asyncio.sleep(0.55)
                    break

            detail = await _read_contact_detail_panel(page)
            if not detail:
                continue

            name_key = (detail.get("full_name") or "").lower()
            target = None
            for c in enriched:
                if c.get("full_name", "").lower() == name_key:
                    target = c
                    break
            if target is None and idx < len(enriched):
                target = enriched[idx]

            if target is None:
                continue

            for key in ("email", "location", "title", "phone", "mobile"):
                val = detail.get(key)
                if val and not target.get(key if key != "mobile" else "phone"):
                    target[key if key != "mobile" else "phone"] = val
            if target.get("email"):
                target["has_email"] = True
            target["detail_panel_fetched"] = True

            for close_pattern in (
                re.compile(r"^close$", re.I),
                re.compile(r"back to results", re.I),
            ):
                close_btn = page.get_by_role("button", name=close_pattern)
                if await close_btn.count() > 0:
                    await close_btn.first.click(timeout=3_000)
                    await asyncio.sleep(0.3)
                    break
        except Exception:
            continue

    return enriched


async def _ensure_contacts_search_ready(page) -> None:
    """Wait for search UI; click sidebar link if the form is not mounted yet."""
    if await _search_form_visible(page):
        return

    for link_text in ("Search Contacts", "Search contacts"):
        link = page.get_by_role("link", name=link_text).first
        try:
            if await link.count() > 0:
                await link.click(timeout=5_000)
                await asyncio.sleep(0.8)
                break
        except Exception:
            continue

    if not await _search_form_visible(page):
        await page.goto(CONTACTS_SEARCH_URL, wait_until="domcontentloaded", timeout=60_000)

    await _wait_for_search_ui(page)


async def _search_form_visible(page) -> bool:
    try:
        if await page.get_by_role("button", name=re.compile(r"^Search$", re.I)).count() == 0:
            return False
        _, count = await _main_search_fields(page)
        return count >= 2
    except Exception:
        return False


async def _wait_for_search_ui(page, *, timeout_ms: int = 25_000) -> None:
    search_btn = page.get_by_role("button", name=re.compile(r"^Search$", re.I)).first
    try:
        await search_btn.wait_for(state="visible", timeout=timeout_ms)
    except Exception as exc:
        raise CareerShiftSearchError(
            "CareerShift search form did not load (Search button missing). "
            "Re-login: python scripts/careershift_login.py --force"
        ) from exc

    deadline = asyncio.get_running_loop().time() + (timeout_ms / 1000)
    while asyncio.get_running_loop().time() < deadline:
        if await _search_form_visible(page):
            return
        await asyncio.sleep(0.25)

    raise CareerShiftSearchError(
        "CareerShift search fields not found. The contacts page UI may have changed."
    )


async def _main_search_fields(page):
    """Visible Name / School / Company fields in the search bar."""
    search_btn = page.get_by_role("button", name=re.compile(r"^Search$", re.I)).first
    if await search_btn.count() > 0:
        bar_inputs = search_btn.locator(
            'xpath=ancestor::*[.//input or .//*[@role="textbox"] or .//*[@role="combobox"]][1]'
        ).locator('input:visible, [role="combobox"]:visible, [role="textbox"]:visible')
        bar_count = await bar_inputs.count()
        if bar_count >= 2:
            return bar_inputs, bar_count

    for root_sel in ("main", '[class*="content" i]', "body"):
        root = page.locator(root_sel).first
        fields = root.locator('input:visible, [role="combobox"]:visible, [role="textbox"]:visible')
        count = await fields.count()
        if count >= 2:
            return fields, count

    fields = page.locator('input:visible, [role="combobox"]:visible, [role="textbox"]:visible')
    return fields, await fields.count()


async def _type_into_field(field, value: str) -> None:
    await field.scroll_into_view_if_needed()
    await field.click()
    try:
        await field.fill("")
        await field.fill(value)
    except Exception:
        await field.press("Control+A")
        await field.press("Backspace")
        await field.press_sequentially(value, delay=35)


async def _clear_search_fields(page) -> None:
    for placeholder in ("Name", "School Attended"):
        try:
            field = page.get_by_placeholder(placeholder).first
            if await field.count() > 0:
                await field.fill("")
        except Exception:
            pass


async def _enable_advanced_search(page) -> None:
    switch = page.get_by_role("switch").first
    try:
        if await switch.count() > 0:
            if not await switch.is_checked():
                await switch.check()
            return
    except Exception:
        pass

    for locator in (
        page.locator('label:has-text("Advanced")'),
        page.get_by_text("Advanced", exact=True),
    ):
        try:
            if await locator.count() > 0:
                await locator.first.click()
                await asyncio.sleep(0.4)
                return
        except Exception:
            continue


async def _fill_by_placeholder(page, pattern: re.Pattern[str], value: str) -> bool:
    field = page.get_by_placeholder(pattern).first
    try:
        if await field.count() == 0:
            return False
        await field.wait_for(state="visible", timeout=5_000)
        await _type_into_field(field, value)
        return True
    except Exception:
        return False


async def _click_search(page) -> None:
    btn = page.get_by_role("button", name="Search", exact=True)
    try:
        async with page.expect_response(
            lambda r: _CONTACTS_API_PATH in r.url.lower() and r.status < 400,
            timeout=20_000,
        ):
            await btn.click(timeout=8_000)
    except Exception:
        await btn.click(timeout=8_000)
        await asyncio.sleep(1.5)


async def _page_has_no_results(page) -> bool:
    try:
        return await page.get_by_text("No Contacts Found", exact=False).count() > 0
    except Exception:
        return False


async def _wait_for_results(page, *, company_name: str, timeout_ms: int = 20_000) -> None:
    """Wait until CareerShift shows results OR an explicit empty state."""
    _ = company_name
    terminal = page.get_by_text(re.compile(r"Contacts Found|No Contacts Found", re.I))
    try:
        await terminal.first.wait_for(state="visible", timeout=timeout_ms)
    except Exception:
        await asyncio.sleep(1.0)


async def _assert_company_results(page, *, company_name: str) -> None:
    _ = page, company_name


async def _parse_results_from_dom(page, *, max_results: int = 25) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    cards = page.locator(_RESULT_CARD)
    count = await cards.count()

    for idx in range(min(count, max_results * 2)):
        try:
            text = (await cards.nth(idx).inner_text()).strip()
        except Exception:
            continue
        parsed = _parse_result_card_text(text)
        if parsed:
            rows.append(parsed)
        if len(rows) >= max_results:
            break

    return rows


def _parse_result_card_text(text: str) -> dict[str, Any] | None:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if len(lines) < 2:
        return None
    name = lines[0]
    if not _looks_like_person_name(name):
        return None
    meta = lines[1]
    if "|" not in meta:
        return None
    company, _, title = meta.partition("|")
    company = company.strip()
    title = title.strip()
    return {
        "careershift_id": _stable_id({"full_name": name, "title": title, "company": company}),
        "full_name": name,
        "company": company or None,
        "title": title or None,
    }


def _normalize_api_contact(row: dict[str, Any]) -> dict[str, Any]:
    loc_parts = [row.get("city"), row.get("state"), row.get("country")]
    location = row.get("location") or ", ".join(str(p) for p in loc_parts if p) or None
    cs_id = row.get("externalId") or row.get("lookupKey") or row.get("id")
    full = (row.get("name") or f"{row.get('firstName', '')} {row.get('lastName', '')}").strip()
    email = row.get("email")
    if isinstance(email, str) and email.lower() == "email@example.com":
        email = None
    company = row.get("companyName") or row.get("company")
    if isinstance(company, dict):
        company = company.get("companyName")
    return {
        "careershift_id": str(cs_id) if cs_id else _stable_id({"full_name": full}),
        "full_name": full or "Unknown",
        "title": row.get("jobTitle") or row.get("title"),
        "email": email,
        "location": location,
        "linkedin_url": row.get("linkedinUrl"),
        "company": company,
        "school": row.get("schoolAttended"),
        "has_email": bool(row.get("hasEmail") or email),
    }


async def _read_contact_detail_panel(page) -> dict[str, Any] | None:
    email = await _read_label_value(page, "Email")
    location = await _read_label_value(page, "Location")
    title = await _read_label_value(page, "Title") or await _read_label_value(page, "Job Title")
    phone = await _read_label_value(page, "Mobile") or await _read_label_value(page, "Phone")

    name = None
    for sel in ("main h1", "main h2", '[class*="contact"] h1', '[class*="contact"] h2'):
        loc = page.locator(sel).first
        try:
            if await loc.count() > 0:
                name = (await loc.inner_text()).strip()
                if name and _looks_like_person_name(name):
                    break
        except Exception:
            continue

    if not email and not name:
        return None

    return {
        "full_name": name or "Unknown",
        "title": title,
        "email": email,
        "location": location,
        "phone": phone,
        "mobile": phone,
    }


async def _read_label_value(page, label: str) -> str | None:
    for selector in (
        f'tr:has-text("{label}") td >> nth=1',
        f'text="{label}" >> xpath=following-sibling::*[1]',
        f'[aria-label="{label}"]',
    ):
        loc = page.locator(selector).first
        try:
            if await loc.count() == 0:
                continue
            value = (await loc.inner_text()).strip()
            if value and value.lower() != label.lower():
                return value
        except Exception:
            continue

    try:
        body = await page.locator("main").inner_text()
    except Exception:
        return None
    lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
    for idx, line in enumerate(lines):
        if line.lower() == label.lower() and idx + 1 < len(lines):
            nxt = lines[idx + 1].strip()
            if nxt and nxt.lower() != label.lower():
                return nxt
    return None


def _looks_like_person_name(text: str) -> bool:
    t = text.strip()
    if not t or len(t) > 80:
        return False
    lower = t.lower()
    skip = {
        "search",
        "advanced",
        "email",
        "location",
        "recommended contacts",
        "save search",
        "generate outreach",
        "search linkedin",
        "company details",
        "current workplace",
        "save contact",
        "copy link",
    }
    if lower in skip or any(s in lower for s in ("recommended contacts", "try advanced")):
        return False
    if "@" in t:
        return False
    parts = t.split()
    return len(parts) >= 2 and parts[0][0].isalpha() and parts[1][0].isalpha()


def _extract_contacts_from_json(data: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    _walk_json(data, found)
    return [_normalize_contact_row(row) for row in found if _looks_like_contact(row)]


def _walk_json(node: Any, found: list[dict[str, Any]], *, depth: int = 0) -> None:
    if depth > 8:
        return
    if isinstance(node, list):
        if node and all(isinstance(x, dict) for x in node[:5]):
            if any(_looks_like_contact(x) for x in node[:5]):
                found.extend(x for x in node if isinstance(x, dict))
                return
        for item in node:
            _walk_json(item, found, depth=depth + 1)
        return
    if not isinstance(node, dict):
        return

    for key in ("contacts", "results", "items", "data", "rows", "Records", "records"):
        child = node.get(key)
        if child is not None:
            _walk_json(child, found, depth=depth + 1)

    if _looks_like_contact(node):
        found.append(node)


def _looks_like_contact(row: dict[str, Any]) -> bool:
    keys = {k.lower() for k in row.keys()}
    name_keys = {"name", "fullname", "full_name", "firstname", "first_name", "contactname"}
    email_keys = {"email", "emailaddress", "email_address", "workemail"}
    title_keys = {"title", "jobtitle", "job_title", "position"}
    if keys & name_keys and (keys & email_keys or keys & title_keys):
        return True
    if "contactid" in keys or "personid" in keys:
        return True
    return False


def _normalize_contact_row(row: dict[str, Any]) -> dict[str, Any]:
    def pick(*names: str) -> str | None:
        for name in names:
            for key, value in row.items():
                if key.lower() == name.lower() and value:
                    return str(value).strip()
        return None

    first = pick("firstName", "first_name", "FirstName")
    last = pick("lastName", "last_name", "LastName")
    full = pick("name", "fullName", "full_name", "contactName", "ContactName")
    if not full and (first or last):
        full = f"{first or ''} {last or ''}".strip()

    location = pick("location", "cityState", "city_state", "metro")
    city = pick("city", "City")
    state = pick("state", "State")
    if not location and (city or state):
        location = ", ".join(p for p in (city, state) if p)

    cs_id = pick("contactId", "contact_id", "personId", "person_id", "id", "Id")

    return {
        "careershift_id": cs_id or _stable_id({"full_name": full, "title": pick("title")}),
        "full_name": full or "Unknown",
        "title": pick("title", "jobTitle", "job_title", "position", "Position"),
        "email": pick("email", "emailAddress", "email_address", "workEmail", "WorkEmail"),
        "company": pick("company", "companyName", "company_name", "organization", "Organization"),
        "location": location,
        "linkedin_url": pick("linkedInUrl", "linkedin_url", "linkedin", "LinkedIn"),
        "school": pick("school", "schoolName", "school_name", "School"),
    }


def _row_texts_to_contact(cells: list[str]) -> dict[str, Any] | None:
    if len(cells) < 2:
        return None
    name = cells[0]
    title = cells[1] if len(cells) > 1 else None
    company = cells[2] if len(cells) > 2 else None
    location = cells[3] if len(cells) > 3 else None
    email = None
    for cell in cells:
        if "@" in cell:
            email = cell.strip()
            break
    if not name or name.lower() in ("name", "contact"):
        return None
    return {
        "careershift_id": _stable_id({"full_name": name, "title": title, "email": email}),
        "full_name": name,
        "title": title,
        "company": company,
        "location": location,
        "email": email,
    }


def _block_text_to_contact(text: str) -> dict[str, Any] | None:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if len(lines) < 2:
        return None
    email = next((ln for ln in lines if "@" in ln), None)
    return {
        "careershift_id": _stable_id({"full_name": lines[0], "title": lines[1], "email": email}),
        "full_name": lines[0],
        "title": lines[1],
        "email": email,
        "location": lines[2] if len(lines) > 2 else None,
    }


def _dedupe_contacts(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for row in rows:
        normalized = _normalize_contact_row(row) if _looks_like_contact(row) else row
        key = (
            normalized.get("careershift_id")
            or normalized.get("email")
            or _stable_id(normalized)
        )
        key = str(key).lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(normalized)
    return out


def _display_name(person: dict[str, Any]) -> str:
    name = (person.get("name") or person.get("full_name") or "").strip()
    if name:
        return name
    first = (person.get("first_name") or person.get("firstName") or "").strip()
    last = (person.get("last_name") or person.get("lastName") or "").strip()
    return f"{first} {last}".strip() or "Unknown"


def _split_name(full: str) -> tuple[str, str]:
    parts = full.split()
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], " ".join(parts[1:])


def _city_from_location(location: str | None) -> str | None:
    if not location:
        return None
    return location.split(",")[0].strip() or None


def _state_from_location(location: str | None) -> str | None:
    if not location or "," not in location:
        return None
    return location.split(",", 1)[1].strip().split()[0] or None


def _stable_id(row: dict[str, Any]) -> str:
    base = "|".join(
        str(row.get(k) or "")
        for k in ("full_name", "name", "title", "email", "company")
    ).lower()
    base = re.sub(r"\s+", " ", base).strip()
    return str(abs(hash(base)))


def login_url() -> str:
    return APP_LOGIN_URL


def signup_url_cmu() -> str:
    return CMU_SIGNUP_URL


def profile_dir() -> Path:
    return PROFILE_DIR
