"""Tests for LLM activity formatting."""

from openrole.llm.tracking import format_llm_activity


def test_format_llm_activity_ingestion():
    line = format_llm_activity("batch enrich · 6 jobs", ingestion=True)
    assert line.startswith("[")
    assert "] ingestion · batch enrich · 6 jobs" in line
    assert "LLM" not in line
