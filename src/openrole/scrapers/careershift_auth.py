"""Strict CareerShift session detection (avoid false positives on login pages)."""

from __future__ import annotations

from urllib.parse import urlparse

from patchright.async_api import Page

# Current CareerShift app (2025+)
APP_BASE_URL = "https://app.careershift.com"
CONTACTS_SEARCH_URL = f"{APP_BASE_URL}/contacts/search"

# Legacy host (redirects or old bookmarks)
LEGACY_BASE_URL = "https://www.careershift.com"
LEGACY_CONTACTS_SEARCH_URL = f"{LEGACY_BASE_URL}/App/Contacts/Search"
LEGACY_LOGIN_URL = f"{LEGACY_BASE_URL}/Account/Login"
CMU_SIGNUP_URL = f"{LEGACY_BASE_URL}/user/signup?group=CMU"

# App login — CareerShift may redirect www → app after auth
APP_LOGIN_URL = f"{APP_BASE_URL}/login"

_LOGIN_PATH_FRAGMENTS = (
    "/account/login",
    "/login",
    "/sign-in",
    "/signin",
    "/user/signup",
    "/forgotpassword",
    "/forgot-password",
)

_APP_PATH_PREFIXES = (
    "/contacts",
    "/jobs",
    "/companies",
    "/campaigns",
    "/documents",
    "/home",
    "/dashboard",
    "/app/",
)

_LOGIN_BODY_PHRASES = (
    "Member Login",
    "Log in to CareerShift",
    "Sign in to CareerShift",
)


def _is_login_url(url: str) -> bool:
    path = (urlparse(url).path or "/").lower()
    if path in ("/login", "/signin", "/sign-in"):
        return True
    lower = url.lower()
    return any(fragment.lower() in lower for fragment in _LOGIN_PATH_FRAGMENTS)


def _is_app_host(host: str) -> bool:
    h = host.lower()
    return h == "app.careershift.com" or h.endswith(".app.careershift.com")


def _is_app_url(url: str) -> bool:
    parsed = urlparse(url)
    path = (parsed.path or "/").lower()
    host = parsed.netloc.lower()

    if _is_app_host(host):
        if _is_login_url(url):
            return False
        if path == "/" or any(path.startswith(prefix) for prefix in _APP_PATH_PREFIXES):
            return True
        # Any non-login route on the app subdomain counts as authenticated shell.
        return bool(path.strip("/"))

    # Legacy www host
    return path.startswith("/app/")


async def session_is_ready(page: Page) -> bool:
    """True only when CareerShift shows a authenticated member session."""
    url = page.url
    host = urlparse(url).netloc.lower()
    if host and "careershift.com" not in host:
        return False
    if _is_login_url(url):
        return False

    try:
        body = await page.evaluate("() => document.body?.innerText || ''")
        title = (await page.title()).strip().lower()
    except Exception:
        return False

    if not isinstance(body, str) or not body.strip():
        return False
    if "member login" in title or title == "login":
        return False
    if any(phrase in body for phrase in _LOGIN_BODY_PHRASES) and not _is_app_url(url):
        return False

    return _is_app_url(url)
