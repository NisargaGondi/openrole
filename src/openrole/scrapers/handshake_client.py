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
import os
import sys
from pathlib import Path
from typing import Any

from openrole.schemas.job import ParsedJob
from openrole.scrapers.url_detect import JobUrlInfo

PROFILE_DIR = Path.home() / ".handshake-mcp" / "profile"

_PATCHRIGHT_BROWSER_HINT = (
    "Patchright Chromium is missing. Run once:\n"
    "  bash scripts/install_handshake.sh\n"
    "or: python -m patchright install chromium"
)


class HandshakeNotConfiguredError(RuntimeError):
    pass


class HandshakeMCPError(RuntimeError):
    pass


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


def _handshake_mcp_argv() -> list[str]:
    """CLI args for the local Handshake MCP subprocess."""
    argv = ["-m", "handshake_mcp_server", "--transport", "stdio"]
    # Cloudflare blocks Patchright in headless mode on macOS; login uses headed browser too.
    headless_env = os.environ.get("OPENROLE_HANDSHAKE_HEADLESS")
    if headless_env is not None:
        if headless_env.lower() not in ("1", "true", "yes"):
            argv.append("--no-headless")
    elif sys.platform == "darwin":
        argv.append("--no-headless")
    return argv


def fetch_from_handshake(info: JobUrlInfo) -> ParsedJob:
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

    payload = _call_tool_sync("get_job_details", {"job_id": info.job_id})
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


def _call_tool_sync(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    return asyncio.run(_call_tool_async(tool_name, arguments))


async def _call_tool_async(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    # stdio only — never HTTP / remote MCP (keeps cookies on localhost).
    server_params = StdioServerParameters(
        command=sys.executable,
        args=_handshake_mcp_argv(),
        env=None,
    )

    async with stdio_client(server_params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)

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
    if "Cloudflare" in msg:
        msg += (
            "\n\nHandshake blocked headless scraping. OpenRole launches a visible browser on macOS; "
            "retry in a few seconds or re-login: python scripts/handshake_login.py"
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
