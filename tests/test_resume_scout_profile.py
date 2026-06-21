"""Tests for resume-derived scout profile."""

from openrole.agents.resume_scout_profile import (
    build_scout_resume_profile,
    job_matches_resume,
)


def test_ml_resume_derives_search_terms():
    text = """
    Machine Learning Engineer Intern
    Skills: PyTorch, TensorFlow, NLP, LLM fine-tuning, Python
  Experience building deep learning pipelines for computer vision.
    """
    prof = build_scout_resume_profile(text=text, label="resume_ML.pdf")
    assert any("machine learning" in t.lower() for t in prof.search_terms)
    assert "pytorch" in prof.skills


def test_ml_resume_matches_ml_job():
    prof = build_scout_resume_profile(
        text="Machine Learning Engineer. PyTorch, NLP, LLM training.",
        label="ml_resume.pdf",
    )
    ok, hits, matched = job_matches_resume(
        "We use PyTorch and NLP for LLM training pipelines.",
        "Machine Learning Engineer",
        prof,
    )
    assert ok
    assert hits > 0
    assert "pytorch" in matched or "nlp" in matched


def test_ml_resume_rejects_unrelated_job():
    prof = build_scout_resume_profile(
        text="Machine Learning Engineer. PyTorch, NLP.",
        label="ml_resume.pdf",
    )
    ok, _, _ = job_matches_resume(
        "Manage wealth operations and client portfolios.",
        "Manager, Wealth Operations",
        prof,
    )
    assert not ok
