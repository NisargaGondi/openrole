"""Tests for scout job prepare and OPT fixes."""

from openrole.agents.scout_filter import RejectReason, assess_opt_status, evaluate_scout_job
from openrole.agents.scout_job_prepare import is_low_quality_job_description
from openrole.config import Settings
from openrole.schemas.job import ParsedJob


def _settings(**kwargs) -> Settings:
    defaults = {
        "database_url": "sqlite:///:memory:",
        "scout_require_opt_mention": True,
    }
    defaults.update(kwargs)
    return Settings.model_construct(**defaults)


def test_spa_garbage_detected():
    text = (
        '=== STRUCTURED PAGE METADATA ===\nTitle: Eng\n'
        '{"themeOptions": {"customTheme": {"varTheme": {"primary-color": "#2C8CC9"}}}}'
        '"title": "Visa sponsorship", "description": "We have a corporate visa sponsorship programme"'
    )
    assert is_low_quality_job_description(text)


def test_assess_opt_unknown_on_spa_garbage_not_eligible():
    text = (
        '{"themeOptions": {}} "title": "Visa sponsorship", '
        '"description": "We have a corporate visa sponsorship programme"'
    )
    assert assess_opt_status(text, None) == "unknown"


def test_mayo_style_sponsorship_language_ineligible():
    text = (
        "Authorization to work and remain in the United States, without necessity for "
        "Mayo Clinic sponsorships now, or in the future. Mayo Clinic does not participate "
        "in the F-1 STEM OPT extension program"
    )
    assert assess_opt_status(text, None) == "ineligible"


def test_evaluate_rejects_after_llm_ineligible():
    job = ParsedJob(
        title="Security Engineer",
        company_name="Mayo Clinic",
        description="<p>Security role.</p>",
        raw_payload={
            "llm_enrich": {
                "visa_status": "ineligible",
                "work_auth_us_only": True,
                "visa_notes": "No sponsorship; does not participate in F-1 STEM OPT.",
            }
        },
    )
    profile = {"scout_resume_profile": None, "resumes": []}
    verdict = evaluate_scout_job(
        job,
        profile=profile,
        settings=_settings(scout_min_relevance_score=0),
    )
    assert not verdict.passed
    assert verdict.reject_reason == RejectReason.OPT_INELIGIBLE


def test_clean_jd_still_accepts_stem_opt():
    text = "PyTorch ML role. STEM OPT and visa sponsorship available for qualified candidates."
    assert assess_opt_status(text, None) == "eligible"


def test_description_sufficient_for_scout_removed():
    """Placeholder — LLM skip for long descriptions removed in favor of batch enrich."""
    assert True
