"""Render job descriptions (plain text or HTML from ATS boards)."""

from __future__ import annotations

import re
from html import unescape

import streamlit as st


def looks_like_html(text: str) -> bool:
    return bool(re.search(r"</?(?:p|div|ul|ol|li|h[1-6]|br|strong|em)\b", text, re.I))


def sanitize_job_html(html: str) -> str:
    """Drop scripts/iframes; keep typical ATS formatting tags."""
    cleaned = re.sub(r"(?is)<script[^>]*>.*?</script>", "", html)
    cleaned = re.sub(r"(?is)<style[^>]*>.*?</style>", "", cleaned)
    cleaned = re.sub(r"(?is)<iframe[^>]*>.*?</iframe>", "", cleaned)
    cleaned = re.sub(r"\s+on\w+\s*=\s*[\"'][^\"']*[\"']", "", cleaned, flags=re.I)
    return cleaned.strip()


def html_to_plain_text(html: str) -> str:
    text = re.sub(r"(?is)<br\s*/?>", "\n", html)
    text = re.sub(r"(?is)</p>", "\n\n", text)
    text = re.sub(r"(?is)<li[^>]*>", "\n• ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    return re.sub(r"\n{3,}", "\n\n", re.sub(r"[ \t]+", " ", text)).strip()


def render_job_description(description: str | None) -> None:
    st.markdown("#### Job description")
    if not description or not str(description).strip():
        st.info("No description stored for this role.")
        return

    text = str(description).strip()
    if looks_like_html(text):
        safe = sanitize_job_html(text)
        st.markdown(
            f'<div class="or-job-description">{safe}</div>',
            unsafe_allow_html=True,
        )
        with st.expander("Plain text view"):
            st.text(html_to_plain_text(text))
    else:
        st.markdown(text)
