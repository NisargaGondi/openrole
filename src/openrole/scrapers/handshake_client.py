"""Secure local Handshake access via the handshake-mcp-server (stdio only).

Security model:
- Runs MCP server as a local subprocess (same machine, no remote HTTP).
- Uses your saved session in ~/.handshake-mcp/profile (never sent to OpenRole code).
- Does not expose MCP over the network; stdio transport only.
- You must run `python -m handshake_mcp_server --login` once with your CMU account.
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

from openrole.schemas.job import ParsedJob
from openrole.scrapers.browser_headless import scrape_headless_enabled
from openrole.scrapers.url_detect import JobUrlInfo

PROFILE_DIR = Path.home() / ".handshake-mcp" / "profile"

_PATCHRIGHT_BROWSER_HINT = (
    "Patchright Chromium is missing. Run once:\n"
    "  bash scripts/install_handshake.sh\n"
    "or: python -m patchright install chromium"
)

_MAX_MCP_RETRIES = 3
_MCP_TOOL_TIMEOUT_SEC = 120.0
_DETAIL_FETCH_DELAY_SEC = 2.5
_WAIT_RE = re.compile(r"wait\s+(\d+)\s+seconds?", re.IGNORECASE)


class HandshakeNotConfiguredError(RuntimeError):
    pass


class HandshakeMCPError(RuntimeError):
    pass


def public_handshake_job_url(job_id: str) -> str:
    """Public share URL — often scrapeable without authenticated MCP."""
    return f"https://app.joinhandshake.com/public/jobs/{job_id}"


def _parse_rate_limit_wait(message: str) -> int | None:
    match = _WAIT_RE.search(message)
    if not match:
        return None
    try:
        return max(1, int(match.group(1)))
    except ValueError:
        return None


def _is_retryable_mcp_error(message: str) -> bool:
    lower = message.lower()
    return (
        "rate limit" in lower
        or "cloudflare" in lower
        or "try again" in lower
        or "too many requests" in lower
    )


def handshake_profile_ready() -> bool:
    return PROFILE_DIR.exists() and any(PROFILE_DIR.iterdir())


def handshake_mcp_installed() -> bool:
    try:
        import handshake_mcp_server  # noqa: F401

        return True
    except ImportError:
        return False


def patchright_browser_ready() -> bool:
    """True when Patchright's Chromium binary is present (required for --login)."""
    cache_dirs = (
        Path.home() / "Library" / "Caches" / "ms-playwright",
        Path.home() / ".cache" / "ms-playwright",
    )
    chrome_names = (
        Path("chrome-mac-arm64")
        / "Google Chrome for Testing.app"
        / "Contents"
        / "MacOS"
        / "Google Chrome for Testing",
        Path("chrome-linux") / "chrome",
        Path("chrome-win") / "chrome.exe",
    )
    for cache in cache_dirs:
        if not cache.is_dir():
            continue
        for d in cache.glob("chromium-*"):
            if d.name.startswith("chromium_headless"):
                continue
            for rel in chrome_names:
                if (d / rel).is_file():
                    return True
    return False


def handshake_ready() -> bool:
    return (
        handshake_mcp_installed()
        and patchright_browser_ready()
        and handshake_profile_ready()
    )


def _handshake_mcp_argv(*, headless: bool | None = None) -> list[str]:
    """CLI args for the local Handshake MCP subprocess."""
    argv = ["-m", "handshake_mcp_server", "--transport", "stdio"]
    if headless is None:
        use_headless = scrape_headless_enabled("OPENROLE_HANDSHAKE_HEADLESS", default=False)
    else:
        use_headless = headless
    if not use_headless:
        argv.append("--no-headless")
    return argv


def fetch_from_handshake(info: JobUrlInfo, *, visible_browser: bool = False) -> ParsedJob:
    """Fetch one Handshake job. Use visible_browser=True for manual debug/login flows."""
    if not handshake_mcp_installed():
        raise HandshakeNotConfiguredError(
            "Install Handshake support: pip install 'openrole[handshake]'"
        )
    if not patchright_browser_ready():
        raise HandshakeNotConfiguredError(_PATCHRIGHT_BROWSER_HINT)
    if not info.job_id:
        raise HandshakeMCPError("Could not parse Handshake job ID from URL")
    if not handshake_profile_ready():
        raise HandshakeNotConfiguredError(
            "No Handshake login profile found. Run once:\n"
            "  python scripts/handshake_login.py --clear-profile --force\n"
            "Session stays in ~/.handshake-mcp/profile on your machine only.\n"
            "If login fails with 'Executable doesn't exist', run:\n"
            "  bash scripts/install_handshake.sh"
        )

    payload = _call_tool_sync_once(
        "get_job_details",
        {"job_id": info.job_id},
        headless=False if visible_browser else None,
    )
    parsed = _payload_to_parsed_job(payload, source_url=info.url, job_id=info.job_id)
    if _looks_like_login_page(parsed):
        raise HandshakeMCPError(
            "Handshake session expired or job page redirected to login. "
            "Re-login: python scripts/handshake_login.py"
        )
    return parsed


def search_handshake_events(*, keywords: str = "", max_pages: int = 1) -> dict[str, Any]:
    """Search career fairs / events (for networking track). Local stdio MCP only."""
    if not handshake_profile_ready():
        raise HandshakeNotConfiguredError("Handshake not logged in — run --login first.")
    args: dict[str, Any] = {"keywords": keywords, "max_pages": max_pages}
    return _call_tool_sync("search_events", args)


def _call_tool_sync_once(
    tool_name: str,
    arguments: dict[str, Any],
    *,
    headless: bool | None = None,
) -> dict[str, Any]:
    return _route_call_tool(tool_name, arguments, headless=headless)


def _call_tool_sync(
    tool_name: str,
    arguments: dict[str, Any],
    *,
    headless: bool | None = None,
) -> dict[str, Any]:
    last_error: HandshakeMCPError | None = None
    for attempt in range(1, _MAX_MCP_RETRIES + 1):
        try:
            return _route_call_tool(tool_name, arguments, headless=headless)
        except HandshakeMCPError as exc:
            last_error = exc
            if attempt >= _MAX_MCP_RETRIES or not _is_retryable_mcp_error(str(exc)):
                raise
            wait = _parse_rate_limit_wait(str(exc)) or (10 * attempt)
            time.sleep(wait + 1)
    if last_error is not None:
        raise last_error
    raise HandshakeMCPError(f"Handshake tool {tool_name} failed after retries")


def _route_call_tool(
    tool_name: str,
    arguments: dict[str, Any],
    *,
    headless: bool | None = None,
) -> dict[str, Any]:
    """Prefer Handshake daemon when available; visible-window calls stay one-shot."""
    if headless is False:
        return asyncio.run(_call_tool_async(tool_name, arguments, headless=headless))

    from openrole.scrapers.handshake_ipc import (
        HandshakeDaemonError,
        HandshakeDaemonUnavailable,
        daemon_call_tool,
        prefer_daemon,
        require_daemon,
    )

    if prefer_daemon():
        try:
            return daemon_call_tool(tool_name, arguments)
        except HandshakeDaemonUnavailable:
            if require_daemon():
                raise HandshakeMCPError(
                    "Handshake daemon required but not running. "
                    "It starts automatically during scout/ingest when BROWSER_DAEMON_ON_DEMAND=true."
                ) from None
        except HandshakeDaemonError as exc:
            raise HandshakeMCPError(str(exc)) from exc
    return asyncio.run(_call_tool_async(tool_name, arguments, headless=headless))


async def _call_tool_async(
    tool_name: str,
    arguments: dict[str, Any],
    *,
    headless: bool | None = None,
) -> dict[str, Any]:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    # stdio only — never HTTP / remote MCP (keeps cookies on localhost).
    server_params = StdioServerParameters(
        command=sys.executable,
        args=_handshake_mcp_argv(headless=headless),
        env=None,
    )

    async with stdio_client(server_params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            try:
                result = await asyncio.wait_for(
                    session.call_tool(tool_name, arguments),
                    timeout=_MCP_TOOL_TIMEOUT_SEC,
                )
            except asyncio.TimeoutError as exc:
                raise HandshakeMCPError(
                    f"Handshake tool {tool_name} timed out after {_MCP_TOOL_TIMEOUT_SEC:.0f}s"
                ) from exc

    if result.isError:
        raise HandshakeMCPError(
            f"Handshake tool {tool_name} failed: {_format_mcp_error(result.content)}"
        )

    return _content_to_dict(result.content)


def _format_mcp_error(content: Any) -> str:
    if not content:
        return "Unknown MCP error"
    parts: list[str] = []
    for block in content:
        text = getattr(block, "text", None) or str(block)
        if text:
            parts.append(text)
    msg = " ".join(parts)
    if "Cloudflare" in msg or "rate limit" in msg.lower():
        msg += (
            "\n\nHandshake may be blocking headless scraping. Manual ingest opens a visible "
            "Chrome window; if this persists, re-login: python scripts/handshake_login.py"
        )
    elif "Not authenticated" in msg or "session expired" in msg.lower():
        msg += "\n\nRe-login: python scripts/handshake_login.py"
    return msg


def _content_to_dict(content: Any) -> dict[str, Any]:
    if not content:
        return {}
    block = content[0]
    text = getattr(block, "text", None) or str(block)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return {"raw": text}
    return data if isinstance(data, dict) else {"raw": data}


def _looks_like_login_page(parsed: ParsedJob) -> bool:
    title = (parsed.title or "").lower()
    company = (parsed.company_name or "").lower()
    if "log in" in title or "sign up" in title:
        return True
    if company in ("unknown company", "") and not parsed.description:
        return True
    return False


def _payload_to_parsed_job(payload: dict[str, Any], *, source_url: str, job_id: str) -> ParsedJob:
    meta = payload.get("metadata") or {}
    sections = payload.get("sections") or {}
    description = meta.get("description") or sections.get("job_posting") or sections.get("overview")
    if isinstance(description, list):
        description = "\n".join(str(x) for x in description)

    locations = meta.get("locations") or []
    if isinstance(locations, str):
        locations = [locations]

    salary = meta.get("salary")
    if salary and meta.get("salary_type") == "hourly":
        salary = float(salary) / 100  # Handshake GraphQL uses cents

    return ParsedJob(
        title=meta.get("title") or f"Handshake job {job_id}",
        company_name=meta.get("company") or "Unknown company",
        description=str(description) if description else None,
        department=meta.get("job_type"),
        locations=locations,
        company_domain=None,
        source_url=payload.get("url") or source_url,
        source_platform="handshake",
        apply_url=meta.get("apply_url") or source_url,
        external_id=job_id,
        raw_payload={"metadata": meta, "sections_keys": list(sections.keys()), "salary_usd": salary},
    )


def _search_diagnostic(payload: dict[str, Any]) -> str | None:
    """Explain empty Handshake search results (auth, headless, rate limit)."""
    errors = payload.get("section_errors") or {}
    if isinstance(errors, dict):
        for err in errors.values():
            if isinstance(err, dict):
                msg = err.get("error_message") or err.get("error_type")
                if msg:
                    return str(msg)
    sections = payload.get("sections") or {}
    if isinstance(sections, dict):
        text = str(sections.get("search_results") or "")
        lower = text.lower()
        if "log in" in lower or "sign up" in lower:
            return "session expired — re-run handshake_login.py"
        if "rate limit" in lower or "security verification" in lower:
            return "Cloudflare/rate limit — use visible browser (OPENROLE_HANDSHAKE_HEADLESS=false)"
    if not payload.get("job_ids") and not payload.get("jobs"):
        headless = scrape_headless_enabled("OPENROLE_HANDSHAKE_HEADLESS", default=False)
        if headless:
            return (
                "headless browser blocked by Handshake — set OPENROLE_HANDSHAKE_HEADLESS=false "
                "in .env and restart API"
            )
        return "authenticated search returned 0 jobs — try re-login via handshake_login.py"
    return None


def search_handshake_jobs(
    *,
    keywords: str,
    location: str | None = None,
    max_pages: int = 1,
    max_jobs: int = 15,
    fetch_details: bool = True,
) -> tuple[list[ParsedJob], str | None]:
    """Search Handshake via local MCP. Returns (jobs, diagnostic_if_empty)."""
    if not handshake_ready():
        raise HandshakeNotConfiguredError(
            "Handshake not ready. Use sidebar **Handshake login** or run:\n"
            "  python scripts/handshake_login.py --clear-profile --force"
        )

    args: dict[str, Any] = {"keywords": keywords, "max_pages": max_pages}
    if location:
        args["location"] = location

    payload = _call_tool_sync("search_jobs", args)
    job_ids = [str(j) for j in (payload.get("job_ids") or [])][:max_jobs]

    if not job_ids and payload.get("jobs"):
        for item in payload["jobs"][:max_jobs]:
            if isinstance(item, dict) and item.get("id"):
                job_ids.append(str(item["id"]))

    if not fetch_details:
        cards = [_search_card_to_parsed(item) for item in (payload.get("jobs") or [])[:max_jobs]]
        if not cards and job_ids:
            cards = [
                _search_card_to_parsed({"id": jid, "title": f"Handshake job {jid}"})
                for jid in job_ids[:max_jobs]
            ]
        diagnostic = _search_diagnostic(payload) if not cards else None
        return cards, diagnostic

    out: list[ParsedJob] = []
    for index, job_id in enumerate(job_ids):
        if index > 0:
            time.sleep(_DETAIL_FETCH_DELAY_SEC)
        try:
            detail = _call_tool_sync("get_job_details", {"job_id": job_id})
            url = detail.get("url") or f"https://app.joinhandshake.com/stu/jobs/{job_id}"
            parsed = _payload_to_parsed_job(detail, source_url=url, job_id=job_id)
            if not _looks_like_login_page(parsed):
                out.append(parsed)
        except HandshakeMCPError:
            continue
    diagnostic = _search_diagnostic(payload) if not out else None
    return out, diagnostic


def _search_card_to_parsed(item: dict[str, Any]) -> ParsedJob:
    job_id = str(item.get("id") or item.get("job_id") or "")
    title = item.get("title") or f"Handshake job {job_id}"
    company = item.get("company") or item.get("employer") or "Unknown company"
    url = item.get("url") or f"https://app.joinhandshake.com/stu/jobs/{job_id}"
    return ParsedJob(
        title=title,
        company_name=company,
        description=item.get("description"),
        locations=[item["location"]] if item.get("location") else [],
        source_url=url,
        source_platform="handshake",
        apply_url=url,
        external_id=job_id or None,
        raw_payload={"metadata": item, "search_card": True},
    )
