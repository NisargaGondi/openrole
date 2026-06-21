"""Tests for experience requirement parsing."""

from openrole.agents.experience_fit import (
    experience_fit,
    parse_required_experience_years,
    title_experience_floor,
)


def test_principal_title_floor():
    assert title_experience_floor("Principal Software Engineer") == 6


def test_parse_jd_years():
    text = "6+ years of professional experience. 8+ years in compiler engineering."
    assert parse_required_experience_years(text, "Software Engineer") == 8


def test_experience_mismatch_for_student():
    fits, required, candidate = experience_fit(
        job_text="8+ years of experience in ML systems.",
        title="Principal Software Engineer",
        candidate_years=2.0,
        slack_years=1.0,
    )
    assert required == 8
    assert candidate == 2.0
    assert not fits
