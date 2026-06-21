"""JSON sanitization for DB payloads."""

import datetime

from openrole.util.json_safe import json_safe, json_safe_dict


def test_json_safe_date():
    d = datetime.date(2026, 5, 30)
    assert json_safe(d) == "2026-05-30"


def test_json_safe_nested_pandas_like():
    payload = {"date_posted": datetime.date(2026, 1, 15), "title": "Engineer"}
    out = json_safe_dict(payload)
    assert out["date_posted"] == "2026-01-15"
    assert out["title"] == "Engineer"
