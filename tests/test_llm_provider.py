"""LLM provider routing tests."""

import pytest
from openrole.config import get_settings


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_auto_prefers_vertex_when_ready(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("LLM_PROVIDER", "auto")
    monkeypatch.setenv("GCP_PROJECT_ID", "test-project")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", __file__)
    monkeypatch.setenv("FIREWORKS_API_KEY", "fw-key")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    get_settings.cache_clear()
    assert get_settings().resolved_llm_provider == "vertex"


def test_auto_fireworks_when_no_vertex(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("LLM_PROVIDER", "auto")
    monkeypatch.setenv("GCP_PROJECT_ID", "")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "")
    monkeypatch.setenv("FIREWORKS_API_KEY", "fw-key")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-or-test")
    get_settings.cache_clear()
    assert get_settings().resolved_llm_provider == "fireworks"


def test_explicit_openrouter(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-or-v1-test")
    monkeypatch.setenv("OPENAI_API_BASE", "https://openrouter.ai/api/v1")
    get_settings.cache_clear()
    assert get_settings().resolved_llm_provider == "openrouter"


def test_explicit_fireworks_over_vertex(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("LLM_PROVIDER", "fireworks")
    monkeypatch.setenv("GCP_PROJECT_ID", "test-project")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", __file__)
    monkeypatch.setenv("FIREWORKS_API_KEY", "fw-key")
    get_settings.cache_clear()
    assert get_settings().resolved_llm_provider == "fireworks"


def test_fireworks_model_names(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("LLM_PROVIDER", "fireworks")
    monkeypatch.setenv("FIREWORKS_API_KEY", "fw-key")
    monkeypatch.setenv("FIREWORKS_MODEL_WRITING", "accounts/fireworks/models/deepseek-v4-pro")
    get_settings.cache_clear()
    s = get_settings()
    assert "deepseek-v4-pro" in s.writing_model_name()
