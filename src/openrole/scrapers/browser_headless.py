"""Headless vs visible browser for automated scraping (not login flows)."""

from __future__ import annotations

import os


def scrape_headless_enabled(env_var: str, *, default: bool = True) -> bool:
    """Return True when automated scrapes should run without a visible window."""
    raw = os.environ.get(env_var)
    if raw is None:
        return default
    return raw.strip().lower() not in ("0", "false", "no", "off")
