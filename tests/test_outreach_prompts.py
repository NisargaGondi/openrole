"""Tests for tier-based outreach prompts."""

from openrole.agents.outreach_prompts import (
    build_draft_system_prompt,
    evaluation_criteria_for_tier,
    infer_tier_from_title,
    resolve_contact_tier,
    tier_label,
)
from openrole.db.models import Contact
from openrole.schemas.contact import ContactTier


def test_resolve_tier_from_metadata():
    contact = Contact(
        company_id="c1",
        full_name="Alex",
        title="Engineering Manager",
        metadata_json={"tier": "HIRING_MANAGER"},
    )
    assert resolve_contact_tier(contact) == ContactTier.HIRING_MANAGER


def test_infer_recruiter_tiers():
    assert infer_tier_from_title("Technical Recruiter") == ContactTier.ROLE_RECRUITER
    assert infer_tier_from_title("Talent Acquisition Partner") == ContactTier.GENERAL_RECRUITER


def test_infer_engineer_and_manager():
    assert infer_tier_from_title("Senior Software Engineer") == ContactTier.TEAM_ENGINEER
    assert infer_tier_from_title("Director of Engineering") == ContactTier.HIRING_MANAGER


def test_hiring_manager_prompt_is_technical():
    prompt = build_draft_system_prompt(tier=ContactTier.HIRING_MANAGER)
    assert "technical" in prompt.lower()
    assert "hiring manager" in prompt.lower()


def test_prompt_includes_related_work_and_graduation_close():
    prompt = build_draft_system_prompt(
        tier=ContactTier.HIRING_MANAGER,
        graduation="December 2026",
        role_search="full-time roles",
    )
    assert "resume" in prompt.lower() and "github" in prompt.lower()
    assert "December 2026" in prompt
    assert "full-time roles" in prompt


def test_general_recruiter_prompt_avoids_jargon():
    prompt = build_draft_system_prompt(tier=ContactTier.GENERAL_RECRUITER)
    assert "plain language" in prompt.lower() or "minimize jargon" in prompt.lower()


def test_evaluator_criteria_vary_by_tier():
    hm = evaluation_criteria_for_tier(ContactTier.HIRING_MANAGER)
    hr = evaluation_criteria_for_tier(ContactTier.GENERAL_RECRUITER)
    assert hm != hr
    assert any("jargon" in c.lower() for c in hr)


def test_evaluator_checks_graduation_when_set():
    criteria = evaluation_criteria_for_tier(
        ContactTier.OTHER,
        graduation="December 2026",
        role_search="full-time roles",
    )
    assert any("December 2026" in c for c in criteria)


def test_tier_label():
    assert "recruiter" in tier_label(ContactTier.GENERAL_RECRUITER).lower()
