"""Tests for batch job ingestion LLM."""

from unittest.mock import MagicMock, patch

from openrole.agents.job_ingestion import enrich_parsed_jobs_batch_with_llm
from openrole.schemas.job import ParsedJob


def _job(title: str, desc: str) -> ParsedJob:
    return ParsedJob(
        title=title,
        company_name="Co",
        description=desc,
        source_url=f"https://example.com/{title.replace(' ', '-')}",
        source_platform="indeed",
    )


@patch("openrole.agents.job_ingestion.get_settings")
@patch("openrole.agents.job_ingestion.get_chat_model")
def test_batch_enrich_maps_job_index(mock_model_fn, mock_settings):
    mock_settings.return_value.llm_configured = True
    mock_settings.return_value.scout_ingestion_batch_size = 4
    mock_settings.return_value.scout_llm_parallel_workers = 1

    response = MagicMock()
    response.content = """{
      "jobs": [
        {"job_index": 0, "title": "ML Engineer", "company_name": "Co",
         "description_html": "<p>Full ML JD with STEM OPT.</p>",
         "locations": ["Remote, US"], "visa_status": "eligible", "warnings": []},
        {"job_index": 1, "title": "Sec Engineer", "company_name": "Co",
         "description_html": "<p>Security role.</p>",
         "locations": ["NYC, NY"], "visa_status": "unknown", "warnings": []}
      ]
    }"""
    mock_model_fn.return_value.invoke.return_value = response

    jobs = [
        _job("ML Engineer", "PyTorch ML. STEM OPT available."),
        _job("Sec Engineer", "AppSec and detection engineering."),
    ]
    results, api_calls = enrich_parsed_jobs_batch_with_llm(jobs, batch_size=4)

    assert api_calls == 1
    assert len(results) == 2
    assert results[0][0].title == "ML Engineer"
    assert (results[0][0].raw_payload or {}).get("llm_enrich", {}).get("visa_status") == "eligible"
    assert "<p>" in (results[0][0].description or "")


@patch("openrole.agents.job_ingestion.get_settings")
@patch("openrole.agents.job_ingestion.get_chat_model")
def test_batch_enrich_parallel_preserves_order(mock_model_fn, mock_settings):
    mock_settings.return_value.llm_configured = True
    mock_settings.return_value.scout_ingestion_batch_size = 1
    mock_settings.return_value.scout_llm_parallel_workers = 4

    def _response(title: str):
        response = MagicMock()
        response.content = f"""{{
          "jobs": [
            {{"job_index": 0, "title": "{title}", "company_name": "Co",
             "description_html": "<p>{title} JD.</p>",
             "locations": ["Remote, US"], "visa_status": "eligible", "warnings": []}}
          ]
        }}"""
        return response

    def _invoke_side_effect(messages, **_kwargs):
        text = str(messages)
        for title in ("Role A", "Role B", "Role C"):
            if title in text:
                return _response(title)
        raise AssertionError(f"unexpected batch enrich prompt: {text[:300]}")

    mock_model = MagicMock()
    mock_model.invoke.side_effect = _invoke_side_effect
    mock_model_fn.return_value = mock_model

    jobs = [_job("Role A", "A desc"), _job("Role B", "B desc"), _job("Role C", "C desc")]
    results, api_calls = enrich_parsed_jobs_batch_with_llm(jobs, batch_size=1, max_workers=3)

    assert api_calls == 3
    assert [r[0].title for r in results] == ["Role A", "Role B", "Role C"]
