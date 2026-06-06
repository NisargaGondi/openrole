"""Strict Handshake session detection (upstream is_logged_in false-positives on CF pages)."""

from __future__ import annotations

from urllib.parse import urlparse

from patchright.async_api import Page

_CF_BODY_PHRASES = (
    "Performing security verification",
    "Please wait while we verify",
    "Just a moment",
    "Checking your browser",
    "security service to protect against malicious bots",
)

_INTERIM_PATH_PREFIXES = (
    "/access",
    "/login",
    "/sign_in",
    "/users/sign_in",
    "/configure_auth",
    "/saml",
)


def _is_interim_url(url: str) -> bool:
    if "access_state_id" in url or "cf_challenge" in url:
        return True
    path = urlparse(url).path or "/"
    return any(
        path == prefix or path.startswith(f"{prefix}/") for prefix in _INTERIM_PATH_PREFIXES
    )


async def session_is_ready(page: Page) -> bool:
    """True only when Handshake shows a real authenticated student session."""
    url = page.url
    host = urlparse(url).netloc
    if host and "app.joinhandshake.com" not in host:
        return False
    if _is_interim_url(url):
        return False

    try:
        title = (await page.title()).strip().lower()
        body = await page.evaluate("() => document.body?.innerText || ''")
        cookies = await page.evaluate("() => document.cookie")
    except Exception:
        return False

    if not isinstance(body, str) or not body.strip():
        return False
    if "just a moment" in title:
        return False
    if any(phrase in body for phrase in _CF_BODY_PHRASES):
        return False
    if not isinstance(cookies, str) or "ajs_user_id=" not in cookies:
        return False

    return True
