"""Tests for scout context preview (resume + public links)."""

from unittest.mock import patch

from openrole.tools.scout_context import scout_context_preview


@patch("openrole.tools.scout_context.list_scout_resume_options")
@patch("openrole.tools.scout_context.load_candidate_profile")
def test_scout_context_merges_github_into_terms(mock_profile, mock_options):
    mock_options.return_value = [{"label": "ml.pdf", "is_default": True}]
    mock_profile.return_value = {
        "resumes": [
            {
                "label": "ml.pdf",
                "text": "Machine Learning Engineer. PyTorch, NLP, deep learning pipelines.",
            }
        ],
        "warnings": [],
        "github_summary": "Repo: openrole — AI job search copilot with PyTorch ML pipelines",
        "website_summary": "Portfolio: machine learning engineer building LLM systems",
    }

    preview = scout_context_preview(resume_label="ml.pdf", fetch_links=False)

    assert preview["search_terms"]
    assert "github" in preview["profile_sources"]
    assert "website" in preview["profile_sources"]
    assert any("machine learning" in t.lower() for t in preview["search_terms"])
