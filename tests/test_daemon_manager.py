"""Tests for on-demand browser daemon lifecycle."""

from unittest.mock import patch

from openrole.scrapers.daemon_manager import managed_daemons, on_demand_enabled


def test_on_demand_default_true():
    with patch.dict("os.environ", {}, clear=False):
        assert on_demand_enabled() is True


def test_on_demand_can_disable():
    with patch.dict("os.environ", {"BROWSER_DAEMON_ON_DEMAND": "false"}):
        assert on_demand_enabled() is False


@patch("openrole.scrapers.daemon_manager.stop_daemon_if_managed")
@patch("openrole.scrapers.daemon_manager.ensure_daemon")
def test_managed_daemons_stops_only_started(mock_ensure, mock_stop):
    mock_ensure.side_effect = [True, False]

    with managed_daemons("careershift", "handshake"):
        pass

    assert mock_ensure.call_count == 2
    mock_stop.assert_called_once_with("careershift")


@patch("openrole.scrapers.daemon_manager.stop_daemon_if_managed")
@patch("openrole.scrapers.daemon_manager.ensure_daemon", return_value=False)
def test_managed_daemons_skips_stop_when_not_started(mock_ensure, mock_stop):
    with managed_daemons("careershift"):
        pass
    mock_stop.assert_not_called()
