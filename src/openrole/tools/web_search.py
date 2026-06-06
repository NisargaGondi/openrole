"""Tavily web search wrapper for domain resolution and person research."""

from __future__ import annotations

from typing import Any

import httpx

from openrole.config import get_settings

TAVILY_URL = "https://api.tavily.com/search"


def is_configured() -> bool:
    return bool(get_settings().tavily_api_key)


def search_web(
    query: str,
    *,
    max_results: int = 5,
    search_depth: str = "basic",
) -> list[dict[str, Any]]:
    """Run a Tavily search; returns list of {title, url, content, score}."""
    key = get_settings().tavily_api_key
    if not key:
        return []

    body = {
        "api_key": key,
        "query": query,
        "max_results": min(max_results, 10),
        "search_depth": search_depth,
        "include_answer": True,
    }
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(TAVILY_URL, json=body)
            response.raise_for_status()
            data = response.json()
    except Exception:
        return []

    results: list[dict[str, Any]] = []
    answer = data.get("answer")
    if answer:
        results.append({"title": "summary", "url": "", "content": str(answer), "score": 1.0})
    for row in data.get("results") or []:
        if isinstance(row, dict):
            results.append(
                {
                    "title": row.get("title"),
                    "url": row.get("url"),
                    "content": row.get("content"),
                    "score": row.get("score"),
                }
            )
    return results


def probe_tavily(*, query: str = "CrowdStrike company website") -> dict[str, Any]:
    if not is_configured():
        return {"ok": False, "error": "TAVILY_API_KEY not set"}
    rows = search_web(query, max_results=2)
    return {"ok": bool(rows), "count": len(rows), "sample": rows[0] if rows else None}
