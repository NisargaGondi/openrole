"""Tests for tier-based outreach prompts."""

from openrole.agents.outreach_prompts import (
    build_draft_system_prompt,
    build_evaluator_system_prompt,
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


def test_executive_title_overrides_stale_hiring_manager_metadata():
    contact = Contact(
        company_id="c1",
        full_name="Dave Orr",
        title="Head of Safeguards at Anthropic",
        metadata_json={"tier": "HIRING_MANAGER"},
    )
    assert resolve_contact_tier(contact) == ContactTier.EXECUTIVE


def test_cmu_alumni_override_for_engineer():
    contact = Contact(
        company_id="c1",
        full_name="Angeli J",
        title="Head of Product",
        metadata_json={"tier": "HIRING_MANAGER", "is_cmu_alumni": True},
    )
    assert resolve_contact_tier(contact) == ContactTier.CMU_ALUMNI


def test_cmu_alumni_does_not_override_recruiter():
    contact = Contact(
        company_id="c1",
        full_name="Pat",
        title="Technical Recruiter",
        metadata_json={"tier": "ROLE_RECRUITER", "is_cmu_alumni": True},
    )
    assert resolve_contact_tier(contact) == ContactTier.ROLE_RECRUITER


def test_infer_executive_vs_hiring_manager():
    assert infer_tier_from_title("Head of Safeguards at Anthropic") == ContactTier.EXECUTIVE
    assert infer_tier_from_title("VP of Engineering") == ContactTier.EXECUTIVE
    assert infer_tier_from_title("Engineering Manager, AI Research") == ContactTier.HIRING_MANAGER
    assert infer_tier_from_title("Director of Engineering") == ContactTier.HIRING_MANAGER


def test_infer_recruiter_tiers():
    assert infer_tier_from_title("Technical Recruiter") == ContactTier.ROLE_RECRUITER
    assert infer_tier_from_title("Talent Acquisition Partner") == ContactTier.GENERAL_RECRUITER


def test_infer_engineer():
    assert infer_tier_from_title("Senior Software Engineer") == ContactTier.TEAM_ENGINEER


def test_executive_prompt_is_short_and_routing():
    prompt = build_draft_system_prompt(tier=ContactTier.EXECUTIVE)
    assert "70" in prompt or "100" in prompt
    assert "routing" in prompt.lower() or "who owns hiring" in prompt.lower()


def test_hiring_manager_prompt_is_technical():
    prompt = build_draft_system_prompt(tier=ContactTier.HIRING_MANAGER)
    assert "technical" in prompt.lower() or "builder" in prompt.lower()
    assert "120" in prompt or "150" in prompt


def test_cmu_alumni_prompt_requires_cmu_early():
    prompt = build_draft_system_prompt(tier=ContactTier.CMU_ALUMNI)
    assert "CMU" in prompt or "Carnegie Mellon" in prompt


def test_prompt_includes_research_hook_and_graduation():
    prompt = build_draft_system_prompt(
        tier=ContactTier.HIRING_MANAGER,
        graduation="December 2026",
        role_search="ML engineer roles",
    )
    assert "primary_hook" in prompt.lower() or "research" in prompt.lower()
    assert "December 2026" in prompt


def test_general_recruiter_prompt_avoids_jargon():
    prompt = build_draft_system_prompt(tier=ContactTier.GENERAL_RECRUITER)
    assert "plain language" in prompt.lower() or "jargon" in prompt.lower()


def test_evaluator_criteria_vary_by_tier():
    exec_c = evaluation_criteria_for_tier(ContactTier.EXECUTIVE)
    eng_c = evaluation_criteria_for_tier(ContactTier.TEAM_ENGINEER)
    assert exec_c != eng_c
    assert any("100" in c or "concise" in c.lower() for c in exec_c)


def test_evaluator_cmu_requires_cmu_mention():
    criteria = evaluation_criteria_for_tier(ContactTier.CMU_ALUMNI)
    assert any("CMU" in c for c in criteria)


def test_evaluator_system_prompt_includes_tier():
    prompt = build_evaluator_system_prompt(tier=ContactTier.EXECUTIVE)
    assert "EXECUTIVE" in prompt


def test_tier_label():
    assert "executive" in tier_label(ContactTier.EXECUTIVE).lower()
    assert "recruiter" in tier_label(ContactTier.GENERAL_RECRUITER).lower()
