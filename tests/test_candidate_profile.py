"""Tests for candidate profile loading."""

from pathlib import Path

import openrole.config as config_mod
from openrole.tools.candidate_profile import _github_username, load_candidate_profile


def test_github_username_parse():
    assert _github_username("https://github.com/nisargagondi") == "nisargagondi"
    assert _github_username("https://gitlab.com/foo") is None


def test_load_resume_from_env(tmp_path, monkeypatch):
    resume = tmp_path / "resume.md"
    resume.write_text("# Jane Doe\n\nML engineer at CMU. Built OpenRole pipeline.", encoding="utf-8")

    monkeypatch.setenv("CANDIDATE_NAME", "Jane Doe")
    monkeypatch.setenv("CANDIDATE_RESUME_PATHS", str(resume))
    monkeypatch.setenv("CANDIDATE_LINKEDIN_URL", "https://linkedin.com/in/janedoe")
    config_mod.get_settings.cache_clear()

    profile = load_candidate_profile(fetch_links=False)
    assert profile["name"] == "Jane Doe"
    assert profile["linkedin_url"] == "https://linkedin.com/in/janedoe"
    assert len(profile["resumes"]) == 1
    assert "OpenRole" in profile["resumes"][0]["text"]
    assert "Jane Doe" in profile["prompt_context"]

    config_mod.get_settings.cache_clear()
