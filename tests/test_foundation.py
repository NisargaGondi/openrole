"""Smoke tests for Week 1 foundation."""

from openrole.config import Settings
from openrole.db.session import init_db, session_scope
from openrole.graph.main_graph import run_pipeline


def test_settings_defaults():
    s = Settings(_env_file=None)
    assert s.app_env == "development"
    assert s.is_sqlite is True


def test_init_db_and_stub_graph(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("GCP_PROJECT_ID", "")
    import openrole.db.session as db_session
    from openrole.config import get_settings

    db_session._engine = None
    db_session._SessionLocal = None
    get_settings.cache_clear()

    init_db()
    result = run_pipeline(job_text="Software Engineer\nCompany: Example Co")
    assert result.get("parsed_job")
    assert not result.get("errors")

    from openrole.db.models import Company

    with session_scope() as session:
        session.add(Company(name="Test Co", domain="example.com"))
