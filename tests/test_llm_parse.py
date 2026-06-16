"""Tests for LLM JSON parsing helpers."""

import pytest
from langchain_core.messages import AIMessage

from openrole.llm.parse import LLMJSONError, extract_llm_text, parse_json_object


def test_parse_json_object_from_fence():
    raw = '```json\n{"email": {"body": "hi"}, "linkedin": {"body": "hey"}}\n```'
    data = parse_json_object(raw)
    assert data["email"]["body"] == "hi"


def test_parse_json_object_from_prose():
    raw = 'Here you go:\n{"email": {"body": "x"}, "linkedin": {"body": "y"}}'
    data = parse_json_object(raw)
    assert data["linkedin"]["body"] == "y"


def test_parse_json_object_empty_raises():
    with pytest.raises(LLMJSONError, match="empty"):
        parse_json_object("")


def test_extract_llm_text_from_list_blocks():
    msg = AIMessage(content=[{"type": "text", "text": '{"ok": true}'}])
    assert extract_llm_text(msg) == '{"ok": true}'
