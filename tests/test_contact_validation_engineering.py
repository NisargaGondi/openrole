"""Tests for engineering-role contact validation filters."""

from openrole.agents.contact_validation import wrong_function_for_engineering_job


def test_rejects_sales_leader_for_mle_job():
    reason = wrong_function_for_engineering_job(
        "Head of Sales & BD, Amazon Retail Ad Service",
        job_title="Machine Learning Engineer II",
    )
    assert reason == "non-engineering function for engineering role"


def test_rejects_vp_ads_for_mle_job():
    reason = wrong_function_for_engineering_job(
        "Vice President, Ads, Amazon",
        job_title="Machine Learning Engineer II",
    )
    assert reason == "senior leader outside engineering org"


def test_allows_head_of_safeguards_for_research_engineer_job():
    reason = wrong_function_for_engineering_job(
        "Head of Safeguards at Anthropic",
        job_title="Research Engineer, Safeguards Labs",
    )
    assert reason is None


def test_allows_mle_peer():
    reason = wrong_function_for_engineering_job(
        "Machine Learning Engineer II @ Amazon",
        job_title="Machine Learning Engineer II",
    )
    assert reason is None
