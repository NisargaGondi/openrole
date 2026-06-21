"""Tests for scout run budgeting."""

from openrole.agents.scout_budget import ScoutRunBudget, select_jobs_matching_terms
from openrole.schemas.job import ParsedJob


def test_budget_scales_with_results_per_term():
    b = ScoutRunBudget.from_settings(results_per_term=5, search_terms=["ml engineer", "security"])
    assert b.target_new_ingests == 10
    assert b.max_llm_prepare == 12
    assert b.max_tavily_companies <= 6
    assert b.max_jobs_per_ats_board == 5


def test_select_jobs_matching_terms_limits_board():
    jobs = [
        ParsedJob(title="Software Engineer", company_name="Co", description="backend"),
        ParsedJob(title="Machine Learning Engineer", company_name="Co", description="pytorch"),
        ParsedJob(title="Accountant", company_name="Co", description="finance"),
    ]
    picked = select_jobs_matching_terms(jobs, ["machine learning engineer"], limit=1)
    assert len(picked) == 1
    assert "Machine Learning" in picked[0].title
