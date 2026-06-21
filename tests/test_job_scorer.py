"""Tests for resume-aware job scoring."""

from openrole.agents.job_scorer import build_resume_corpus, score_job_relevance, should_run_resume_analysis
from openrole.schemas.job import ParsedJob


def test_score_high_for_ml_overlap():
    profile = {
        "role_search": "machine learning engineer",
        "resumes": [{"text": "PyTorch deep learning NLP LLM training inference Python"}],
    }
    job = ParsedJob(
        title="Machine Learning Engineer",
        company_name="Acme",
        description="We need PyTorch, deep learning, and LLM inference experience.",
    )
    score = score_job_relevance(job, profile=profile)
    assert score >= 50


def test_score_low_without_overlap():
    profile = {"role_search": "accountant", "resumes": [{"text": "GAAP bookkeeping payroll"}]}
    job = ParsedJob(
        title="Senior ML Researcher",
        company_name="Acme",
        description="Kubernetes distributed systems only.",
    )
    score = score_job_relevance(job, profile=profile)
    assert score < 40


def test_should_run_resume_analysis_threshold():
    assert should_run_resume_analysis(75, threshold=70)
    assert not should_run_resume_analysis(50, threshold=70)


def test_build_resume_corpus_includes_role_search():
    corpus = build_resume_corpus({"role_search": "AI security", "resumes": [{"text": "foo"}]})
    assert "AI security" in corpus
    assert "foo" in corpus
