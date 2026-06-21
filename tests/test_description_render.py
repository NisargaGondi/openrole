"""Tests for job description HTML rendering."""

from openrole.ui.util.description_render import html_to_plain_text, looks_like_html, sanitize_job_html


def test_looks_like_html():
    assert looks_like_html("<p>Hello</p>")
    assert not looks_like_html("Plain text job description.")


def test_html_to_plain_text():
    text = html_to_plain_text("<h2>About</h2><p>Build <strong>ML</strong> systems.</p>")
    assert "About" in text
    assert "ML" in text


def test_sanitize_strips_script():
    safe = sanitize_job_html('<p>OK</p><script>alert(1)</script>')
    assert "script" not in safe.lower()
    assert "OK" in safe
