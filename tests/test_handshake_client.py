"""Tests for Handshake client helpers."""

from unittest.mock import patch

import pytest

from openrole.scrapers.handshake_client import (
    HandshakeMCPError,
    _is_retryable_mcp_error,
    _parse_rate_limit_wait,
    fetch_from_handshake,
    public_handshake_job_url,
)
from openrole.schemas.job import ParsedJob
from openrole.scrapers.url_detect import detect_job_url


def test_public_handshake_job_url():
    assert public_handshake_job_url("11074611") == (
        "https://app.joinhandshake.com/public/jobs/11074611"
    )


def test_parse_rate_limit_wait():
    assert _parse_rate_limit_wait("Rate limit detected. Wait 10 seconds before trying again.") == 10
    assert _parse_rate_limit_wait("no wait here") is None


def test_is_retryable_mcp_error():
    assert _is_retryable_mcp_error("Rate limit detected")
    assert _is_retryable_mcp_error("Cloudflare challenge did not resolve")
    assert not _is_retryable_mcp_error("Session expired")


@patch("openrole.scrapers.handshake_client._call_tool_sync_once")
@patch("openrole.scrapers.handshake_client.handshake_profile_ready", return_value=True)
@patch("openrole.scrapers.handshake_client.patchright_browser_ready", return_value=True)
@patch("openrole.scrapers.handshake_client.handshake_mcp_installed", return_value=True)
def test_fetch_from_handshake_uses_visible_browser(
    _mcp_ok,
    _browser_ok,
    _profile_ok,
    mock_call,
):
    mock_call.return_value = {
        "url": "https://app.joinhandshake.com/stu/jobs/11074611",
        "metadata": {
            "title": "SWE Intern",
            "company": "Acme",
            "description": "Build things",
            "locations": ["Pittsburgh, PA"],
        },
        "sections": {},
    }

    url = "https://app.joinhandshake.com/public/jobs/11074611"
    info = detect_job_url(url)
    result = fetch_from_handshake(info, visible_browser=True)

    assert result.title == "SWE Intern"
    mock_call.assert_called_once()
    assert mock_call.call_args.kwargs.get("headless") is False


@patch("openrole.scrapers.handshake_client._call_tool_sync_once")
@patch("openrole.scrapers.handshake_client.handshake_profile_ready", return_value=True)
@patch("openrole.scrapers.handshake_client.patchright_browser_ready", return_value=True)
@patch("openrole.scrapers.handshake_client.handshake_mcp_installed", return_value=True)
def test_fetch_from_handshake_default_uses_daemon_headless(
    _mcp_ok,
    _browser_ok,
    _profile_ok,
    mock_call,
):
    mock_call.return_value = {
        "url": "https://app.joinhandshake.com/stu/jobs/11074611",
        "metadata": {"title": "SWE Intern", "company": "Acme", "description": "Build things"},
        "sections": {},
    }
    info = detect_job_url("https://app.joinhandshake.com/public/jobs/11074611")
    fetch_from_handshake(info)
    assert mock_call.call_args.kwargs.get("headless") is None


@patch("openrole.scrapers.handshake_client.asyncio.run")
def test_call_tool_sync_retries_rate_limit(mock_run):
    from openrole.scrapers.handshake_client import _call_tool_sync

    mock_run.side_effect = [
        HandshakeMCPError("Rate limit detected. Wait 1 seconds before trying again."),
        {"metadata": {"title": "OK"}},
    ]

    with patch("openrole.scrapers.handshake_client.time.sleep"):
        out = _call_tool_sync("get_job_details", {"job_id": "1"})

    assert out["metadata"]["title"] == "OK"
    assert mock_run.call_count == 2
