"""Shared email sanity checks."""

from __future__ import annotations

import re

_EMAIL_RE = re.compile(r"^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}$", re.I)

_PLACEHOLDER_LOCALS = frozenset(
    {
        "email",
        "example",
        "test",
        "sample",
        "placeholder",
        "noreply",
        "no-reply",
    }
)
_PLACEHOLDER_DOMAINS = frozenset(
    {
        "example.com",
        "email.com",
        "test.com",
        "domain.com",
        "sample.com",
    }
)


def is_placeholder_email(email: str | None) -> bool:
    if not email:
        return False
    raw = str(email).strip().lower()
    if raw in ("email@example.com", "example@example.com", "n/a", "none", "-", ""):
        return True
    if not _EMAIL_RE.match(raw):
        return True
    local, _, domain = raw.partition("@")
    if domain in _PLACEHOLDER_DOMAINS:
        return True
    if local in _PLACEHOLDER_LOCALS:
        return True
    if local.startswith("xxx") or "****" in raw:
        return True
    return False


def clean_email(raw: str | None) -> str | None:
    if not raw:
        return None
    email = str(raw).strip().lower()
    if is_placeholder_email(email):
        return None
    return email if _EMAIL_RE.match(email) else None
