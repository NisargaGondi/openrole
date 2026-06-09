"""Load candidate background from .env paths and public links for outreach drafts."""

from __future__ import annotations

import re
from html import unescape
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from openrole.config import _REPO_ROOT, get_settings

_TEXT_SUFFIXES = {".md", ".txt", ".tex"}
_PDF_SUFFIX = ".pdf"
_MAX_RESUME_CHARS = 12_000
_MAX_WEB_CHARS = 4_000
_HEADERS = {"User-Agent": "OpenRole/0.1 (candidate profile loader)"}


def load_candidate_profile(*, fetch_links: bool = True) -> dict[str, Any]:
    """Build structured candidate context for email/LinkedIn draft writers."""
    settings = get_settings()
    profile: dict[str, Any] = {
        "name": settings.candidate_name,
        "school": settings.cmu_school_name,
        "email_domain": settings.cmu_email_domain,
        "linkedin_url": settings.candidate_linkedin_url,
        "github_url": settings.candidate_github_url,
        "website_url": settings.candidate_website_url,
        "graduation": settings.candidate_graduation,
        "role_search": settings.candidate_role_search,
        "resumes": [],
        "warnings": [],
    }

    legacy = _REPO_ROOT / "data" / "profile.md"
    if legacy.is_file():
        profile["profile_notes"] = legacy.read_text(encoding="utf-8", errors="replace")[:4000]

    for path in settings.candidate_resume_paths_list():
        loaded = _load_resume_file(path)
        if loaded:
            profile["resumes"].append(loaded)
        else:
            profile["warnings"].append(f"Could not read resume: {path}")

    if fetch_links:
        if settings.candidate_github_url:
            gh = _fetch_github_summary(settings.candidate_github_url)
            if gh:
                profile["github_summary"] = gh
            else:
                profile["warnings"].append("GitHub profile fetch failed or URL invalid")
        if settings.candidate_website_url:
            site = _fetch_website_text(settings.candidate_website_url)
            if site:
                profile["website_summary"] = site
            else:
                profile["warnings"].append("Personal website fetch failed")

    profile["prompt_context"] = _build_prompt_context(profile)
    return profile


def profile_status() -> dict[str, Any]:
    """Summary for Settings UI."""
    settings = get_settings()
    paths = settings.candidate_resume_paths_list()
    loaded = sum(1 for p in paths if p.is_file())
    profile = load_candidate_profile(fetch_links=False)
    return {
        "name_set": bool(settings.candidate_name),
        "linkedin_set": bool(settings.candidate_linkedin_url),
        "github_set": bool(settings.candidate_github_url),
        "website_set": bool(settings.candidate_website_url),
        "resume_paths": [str(p) for p in paths],
        "resume_files_found": loaded,
        "graduation_set": bool(settings.candidate_graduation),
        "role_search": settings.candidate_role_search,
        "has_prompt_context": bool(profile.get("prompt_context")),
        "warnings": profile.get("warnings") or [],
    }


def _build_prompt_context(profile: dict[str, Any]) -> str:
    parts: list[str] = []
    if profile.get("name"):
        parts.append(f"Name: {profile['name']}")
    if profile.get("school"):
        parts.append(f"School: {profile['school']}")
    if profile.get("graduation"):
        parts.append(f"Graduation: {profile['graduation']}")
    if profile.get("role_search"):
        parts.append(f"Seeking: {profile['role_search']}")
    for key, label in (
        ("linkedin_url", "LinkedIn"),
        ("github_url", "GitHub"),
        ("website_url", "Website"),
    ):
        if profile.get(key):
            parts.append(f"{label}: {profile[key]}")
    if profile.get("profile_notes"):
        parts.append("Additional notes:\n" + profile["profile_notes"])
    if profile.get("github_summary"):
        parts.append("GitHub (public API):\n" + profile["github_summary"][:2500])
    if profile.get("website_summary"):
        parts.append("Personal site excerpt:\n" + profile["website_summary"][:2500])
    for idx, resume in enumerate(profile.get("resumes") or [], start=1):
        label = resume.get("label") or f"resume_{idx}"
        text = resume.get("text") or ""
        parts.append(f"Resume ({label}):\n{text[: _MAX_RESUME_CHARS]}")
    if not parts:
        parts.append(
            "No candidate profile configured. Set CANDIDATE_* vars in .env "
            "(name, resume paths, LinkedIn, GitHub, website)."
        )
    return "\n\n".join(parts)


def _load_resume_file(path: Path) -> dict[str, str] | None:
    if not path.is_file():
        return None
    suffix = path.suffix.lower()
    try:
        if suffix in _TEXT_SUFFIXES:
            text = path.read_text(encoding="utf-8", errors="replace")
        elif suffix == _PDF_SUFFIX:
            text = _extract_pdf_text(path)
        else:
            return None
    except OSError:
        return None
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return None
    return {"label": path.name, "path": str(path), "text": text[:_MAX_RESUME_CHARS]}


def _extract_pdf_text(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError(
            "PDF resume requires pypdf. Install with: pip install pypdf"
        ) from exc
    reader = PdfReader(str(path))
    chunks: list[str] = []
    for page in reader.pages[:12]:
        chunks.append(page.extract_text() or "")
    return "\n".join(chunks)


def _fetch_github_summary(url: str) -> str | None:
    username = _github_username(url)
    if not username:
        return None
    try:
        with httpx.Client(timeout=20.0, headers=_HEADERS) as client:
            user_resp = client.get(f"https://api.github.com/users/{username}")
            if user_resp.status_code >= 400:
                return None
            user = user_resp.json()
            repos_resp = client.get(
                f"https://api.github.com/users/{username}/repos",
                params={"sort": "updated", "per_page": 5},
            )
            repos = repos_resp.json() if repos_resp.status_code < 400 else []
    except Exception:
        return None

    lines = [
        f"Username: {username}",
        f"Bio: {user.get('bio') or '—'}",
        f"Company: {user.get('company') or '—'}",
        f"Location: {user.get('location') or '—'}",
        f"Public repos: {user.get('public_repos')}",
    ]
    if isinstance(repos, list):
        for repo in repos[:5]:
            if not isinstance(repo, dict):
                continue
            desc = (repo.get("description") or "")[:120]
            lines.append(f"Repo: {repo.get('name')} — {desc}")
    return "\n".join(lines)


def _fetch_website_text(url: str) -> str | None:
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    try:
        with httpx.Client(timeout=20.0, headers=_HEADERS, follow_redirects=True) as client:
            resp = client.get(url)
            resp.raise_for_status()
            html = resp.text
    except Exception:
        return None
    text = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.I | re.S)
    text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(re.sub(r"\s+", " ", text)).strip()
    return text[:_MAX_WEB_CHARS] if text else None


def _github_username(url: str) -> str | None:
    parsed = urlparse(url.strip())
    if "github.com" not in parsed.netloc.lower():
        return None
    parts = [p for p in parsed.path.split("/") if p]
    return parts[0] if parts else None
