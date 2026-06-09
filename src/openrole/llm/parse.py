"""Parse structured JSON from LLM chat responses."""

from __future__ import annotations

import json
import re
from typing import Any


class LLMJSONError(ValueError):
    """LLM response could not be parsed as the expected JSON object."""


def extract_llm_text(response: Any) -> str:
    """Normalize LangChain AIMessage content to plain text."""
    content = getattr(response, "content", response)
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                if block.get("type") == "text" and block.get("text"):
                    parts.append(str(block["text"]))
                elif block.get("text"):
                    parts.append(str(block["text"]))
        joined = "".join(parts).strip()
        if joined:
            return joined
    kwargs = getattr(response, "additional_kwargs", None) or {}
    for key in ("refusal", "reasoning", "reasoning_content"):
        value = kwargs.get(key)
        if value:
            return str(value).strip()
    return str(content or "").strip()


def parse_json_object(content: str, *, error_label: str = "LLM") -> dict[str, Any]:
    """Parse a JSON object from model output, tolerating markdown fences and prose."""
    text = extract_llm_text(content) if not isinstance(content, str) else content.strip()
    if not text:
        raise LLMJSONError(f"{error_label} returned empty content")

    candidates = [text]
    if text.startswith("```"):
        unfenced = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
        unfenced = re.sub(r"\s*```$", "", unfenced).strip()
        if unfenced:
            candidates.insert(0, unfenced)

    match = re.search(r"\{.*\}", text, flags=re.S)
    if match:
        candidates.append(match.group(0))

    last_exc: json.JSONDecodeError | None = None
    seen: set[str] = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError as exc:
            last_exc = exc
            continue
        if not isinstance(data, dict):
            raise LLMJSONError(f"{error_label} JSON must be an object")
        return data

    snippet = text[:200].replace("\n", " ")
    if last_exc is not None:
        raise LLMJSONError(
            f"{error_label} returned invalid JSON: {last_exc.msg}. Snippet: {snippet!r}"
        ) from last_exc
    raise LLMJSONError(f"{error_label} returned invalid JSON. Snippet: {snippet!r}")
