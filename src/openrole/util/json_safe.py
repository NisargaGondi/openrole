"""Make arbitrary Python values safe for SQLAlchemy JSON columns."""

from __future__ import annotations

import datetime
import enum
from decimal import Decimal
from typing import Any


def json_safe(value: Any) -> Any:
    """Recursively convert values to JSON-serializable types."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
        return value.isoformat()
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(v) for v in value]
    # pandas / numpy scalars
    item = getattr(value, "item", None)
    if callable(item):
        try:
            return json_safe(item())
        except Exception:
            pass
    iso = getattr(value, "isoformat", None)
    if callable(iso):
        try:
            return iso()
        except Exception:
            pass
    text = str(value)
    if text in ("nan", "NaT", "None"):
        return None
    return text


def json_safe_dict(value: dict[str, Any] | None) -> dict[str, Any] | None:
    if not value:
        return value
    return json_safe(value)
