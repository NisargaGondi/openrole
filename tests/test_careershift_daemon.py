"""Tests for CareerShift daemon IPC helpers."""

from openrole.scrapers.careershift_ipc import daemon_mode, prefer_daemon, require_daemon


def test_daemon_mode_defaults_auto():
    assert daemon_mode() in ("auto", "off", "always", "true", "false", "1", "0")


def test_prefer_daemon_auto():
    assert prefer_daemon() or daemon_mode() in ("off", "false", "0")


def test_require_daemon_only_when_forced():
    if require_daemon():
        assert prefer_daemon()
