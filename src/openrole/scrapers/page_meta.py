"""Lightweight HTML metadata extraction for job pages."""

from __future__ import annotations

import re

import httpx

_HEADERS = {"User-Agent": "OpenRole/0.1"}


def fetch_page_title(url: str) -> str | None:
    try:
        with httpx.Client(timeout=20.0, headers=_HEADERS, follow_redirects=True) as client:
            response = client.get(url)
            response.raise_for_status()
            html = response.text[:100_000]
    except httpx.HTTPError:
        return None

    for pattern in (
        r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:title',
        r"<title>([^<]+)</title>",
    ):
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None


def parse_linkedin_title(title: str) -> tuple[str | None, str | None]:
    """Parse 'Role at Company' or 'Role - Company' from LinkedIn og:title."""
    for sep in (" at ", " - ", " | "):
        if sep in title:
            left, right = title.split(sep, 1)
            return left.strip(), right.strip()
    return title.strip(), None
