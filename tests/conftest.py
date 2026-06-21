"""Shared pytest fixtures — keep unit tests off the developer's local .env."""

from __future__ import annotations

import pytest

import openrole.config as config_mod
import openrole.db.session as db_session


@pytest.fixture(autouse=True)
def _isolate_env_from_dotenv(monkeypatch):
    """Prevent load_dotenv(override=True) from wiping monkeypatched env vars."""
    monkeypatch.setattr(config_mod, "load_dotenv", lambda *_a, **_k: None)
    config_mod.get_settings.cache_clear()
    db_session._engine = None
    db_session._SessionLocal = None
    yield
    config_mod.get_settings.cache_clear()
    db_session._engine = None
    db_session._SessionLocal = None
