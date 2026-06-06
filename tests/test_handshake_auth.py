"""Tests for strict Handshake session detection."""

from openrole.scrapers.handshake_auth import _is_interim_url


def test_interim_access_url():
    assert _is_interim_url(
        "https://app.joinhandshake.com/access?access_state_id=abc&cf_challenge=1"
    )


def test_interim_login_url():
    assert _is_interim_url("https://app.joinhandshake.com/login")


def test_stu_url_not_interim():
    assert not _is_interim_url("https://app.joinhandshake.com/stu/jobs")
