"""Tests for draft evaluator hard gates."""

from openrole.agents.draft_evaluator import DraftEvaluation, _apply_hard_gates
from openrole.schemas.contact import ContactTier


def test_executive_email_over_limit_fails():
    evaluation = DraftEvaluation(
        acceptable=True,
        grade="good",
        feedback="",
        email_score=90,
        linkedin_score=90,
    )
    long_body = " ".join(["word"] * 150)
    result = _apply_hard_gates(
        evaluation,
        tier=ContactTier.EXECUTIVE,
        email_body=long_body,
        linkedin_body="Short note",
    )
    assert result.acceptable is False
    assert result.grade == "needs_work"
    assert "120" in result.feedback or "100" in result.feedback


def test_linkedin_over_280_fails():
    evaluation = DraftEvaluation(
        acceptable=True,
        grade="good",
        feedback="",
        email_score=90,
        linkedin_score=90,
    )
    result = _apply_hard_gates(
        evaluation,
        tier=ContactTier.TEAM_ENGINEER,
        email_body="Hi there " * 10,
        linkedin_body="x" * 300,
    )
    assert result.acceptable is False
    assert "280" in result.feedback
