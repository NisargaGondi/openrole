"""Tests for scout role + OPT filters."""

from openrole.agents.resume_scout_profile import build_scout_resume_profile
from openrole.agents.scout_filter import RejectReason, evaluate_scout_job
from openrole.config import Settings
from openrole.schemas.job import ParsedJob


def _settings(**kwargs) -> Settings:
    defaults = {
        "database_url": "sqlite:///:memory:",
        "scout_require_opt_mention": True,
    }
    defaults.update(kwargs)
    return Settings.model_construct(**defaults)


def _profile_with_resume(text: str, label: str = "ml.pdf") -> dict:
    scout = build_scout_resume_profile(text=text, label=label)
    return {"resumes": [{"label": label, "text": text}], "scout_resume_profile": scout}


def test_rejects_non_software_title():
    job = ParsedJob(
        title="Manager, Wealth Operations",
        company_name="Bank",
        description="Full-time role. STEM OPT available.",
    )
    profile = _profile_with_resume("Software Engineer Python")
    verdict = evaluate_scout_job(job, profile=profile, settings=_settings())
    assert not verdict.passed
    assert verdict.reject_reason == RejectReason.NOT_SOFTWARE


def test_rejects_resume_mismatch():
    job = ParsedJob(
        title="Software Engineer",
        company_name="Acme",
        description="React marketing dashboards. STEM OPT sponsorship available.",
    )
    profile = _profile_with_resume(
        "Machine Learning Engineer. PyTorch, deep learning, LLM.",
        label="ml.pdf",
    )
    verdict = evaluate_scout_job(job, profile=profile, settings=_settings())
    assert not verdict.passed
    assert verdict.reject_reason == RejectReason.RESUME_MISMATCH


def test_accepts_ml_resume_ml_job_with_opt():
    job = ParsedJob(
        title="Machine Learning Engineer",
        company_name="Acme",
        description="PyTorch, LLM inference. STEM OPT and visa sponsorship available.",
    )
    profile = _profile_with_resume(
        "Machine Learning Engineer. PyTorch, deep learning, NLP, LLM.",
        label="ml.pdf",
    )
    verdict = evaluate_scout_job(job, profile=profile, settings=_settings())
    assert verdict.passed
    assert verdict.opt_status == "eligible"


def test_rejects_no_sponsorship():
    job = ParsedJob(
        title="Security Engineer",
        company_name="Acme",
        description="AppSec. Must be authorized to work without sponsorship.",
    )
    profile = _profile_with_resume("Security engineer. Python, AppSec.")
    verdict = evaluate_scout_job(job, profile=profile, settings=_settings())
    assert not verdict.passed
    assert verdict.reject_reason == RejectReason.OPT_INELIGIBLE


def test_rejects_unknown_opt_when_required():
    job = ParsedJob(
        title="Software Engineer",
        company_name="Acme",
        description="Distributed systems in Python and Kubernetes.",
    )
    profile = _profile_with_resume("Software engineer. Python, Kubernetes, backend.")
    verdict = evaluate_scout_job(job, profile=profile, settings=_settings())
    assert not verdict.passed
    assert verdict.reject_reason == RejectReason.OPT_UNKNOWN


def test_handshake_metadata_opt_eligible():
    from openrole.agents.scout_filter import assess_opt_status

    job = ParsedJob(
        title="Software Engineer",
        company_name="Acme",
        description="Build APIs.",
        raw_payload={"metadata": {"accepts_opt": True, "will_sponsor": True}},
    )
    assert assess_opt_status("Build APIs.", job) == "eligible"


def test_allows_unknown_opt_when_disabled():
    job = ParsedJob(
        title="Software Engineer",
        company_name="Acme",
        description="Distributed systems in Python and Kubernetes.",
    )
    profile = _profile_with_resume("Software engineer. Python, Kubernetes, distributed systems.")
    verdict = evaluate_scout_job(
        job,
        profile=profile,
        settings=_settings(scout_require_opt_mention=False),
    )
    assert verdict.passed


def test_rejects_principal_when_under_experienced():
    job = ParsedJob(
        title="Principal Software Engineer",
        company_name="Microsoft",
        description=(
            "Python, PyTorch, distributed systems, ML inference. "
            "6+ years professional experience required. "
            "8+ years building distributed systems. STEM OPT sponsorship available."
        ),
    )
    profile = _profile_with_resume(
        "Machine Learning Engineer. PyTorch, Python, distributed systems, LLM inference.",
        label="ml.pdf",
    )
    verdict = evaluate_scout_job(
        job,
        profile=profile,
        settings=_settings(candidate_years_experience=2.0),
    )
    assert not verdict.passed
    assert verdict.reject_reason == RejectReason.EXPERIENCE_MISMATCH
