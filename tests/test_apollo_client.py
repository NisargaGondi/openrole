"""Tests for Apollo client helpers."""

from openrole.tools.apollo_client import _name_match_score, _normalize_name_for_match


def test_name_match_score_handles_similar_names():
    left = _normalize_name_for_match("Nikhil Sa")
    right = _normalize_name_for_match("Nikhil Saxena")
    assert left.split()[0] == right.split()[0]


def test_name_match_score_rejects_unrelated():
    assert _name_match_score("jane doe", "john smith") < 0.5
