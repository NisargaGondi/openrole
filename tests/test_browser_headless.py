"""Tests for scrape headless env parsing."""

from openrole.scrapers.browser_headless import scrape_headless_enabled


def test_scrape_headless_default_true(monkeypatch):
    monkeypatch.delenv("OPENROLE_TEST_HEADLESS", raising=False)
    assert scrape_headless_enabled("OPENROLE_TEST_HEADLESS", default=True) is True


def test_scrape_headless_false_values(monkeypatch):
    for val in ("0", "false", "no", "off"):
        monkeypatch.setenv("OPENROLE_TEST_HEADLESS", val)
        assert scrape_headless_enabled("OPENROLE_TEST_HEADLESS", default=True) is False


def test_handshake_mcp_argv_visible_by_default(monkeypatch):
    monkeypatch.delenv("OPENROLE_HANDSHAKE_HEADLESS", raising=False)
    from openrole.scrapers.handshake_client import _handshake_mcp_argv

    assert "--no-headless" in _handshake_mcp_argv()


def test_handshake_mcp_argv_headless_when_enabled(monkeypatch):
    monkeypatch.setenv("OPENROLE_HANDSHAKE_HEADLESS", "true")
    from openrole.scrapers.handshake_client import _handshake_mcp_argv

    assert "--no-headless" not in _handshake_mcp_argv()


def test_handshake_mcp_argv_visible_when_disabled(monkeypatch):
    monkeypatch.setenv("OPENROLE_HANDSHAKE_HEADLESS", "false")
    from openrole.scrapers.handshake_client import _handshake_mcp_argv

    assert "--no-headless" in _handshake_mcp_argv()


def test_handshake_mcp_argv_ingest_forces_visible():
    from openrole.scrapers.handshake_client import _handshake_mcp_argv

    assert "--no-headless" in _handshake_mcp_argv(headless=False)
