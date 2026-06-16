#!/usr/bin/env python3
"""Copy FIREWORKS_* keys from SummerRA/SED/.env into openrole/.env (never overwrites existing)."""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SED_ENV = REPO.parent / "SummerRA" / "SED" / ".env"
OPENROLE_ENV = REPO / ".env"
KEYS = (
    "FIREWORKS_API_KEY",
    "FIREWORKS_BASE_URL",
    "FIREWORKS_MODEL",
    "FIREWORKS_MODEL_DEFAULT",
    "FIREWORKS_MODEL_INGESTION",
    "FIREWORKS_MODEL_WRITING",
    "FIREWORKS_MEMORY_MODEL",
)


def _parse_env(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        out[key.strip()] = val.strip().strip('"').strip("'")
    return out


def main() -> int:
    if not SED_ENV.is_file():
        print(f"SED .env not found at {SED_ENV}")
        print("Set FIREWORKS_API_KEY manually in openrole/.env")
        return 1

    sed = _parse_env(SED_ENV)
    if not sed.get("FIREWORKS_API_KEY"):
        print("FIREWORKS_API_KEY missing in SED .env")
        return 1

    existing = _parse_env(OPENROLE_ENV) if OPENROLE_ENV.is_file() else {}
    to_add: list[str] = []

    mapping = {
        "FIREWORKS_API_KEY": "FIREWORKS_API_KEY",
        "FIREWORKS_BASE_URL": "FIREWORKS_BASE_URL",
        "FIREWORKS_MODEL_DEFAULT": "FIREWORKS_MODEL",
        "FIREWORKS_MODEL_INGESTION": "FIREWORKS_MODEL",
        "FIREWORKS_MODEL_WRITING": "FIREWORKS_MODEL",
    }
    # Normalize SED FIREWORKS_MODEL → our ingestion/default if dedicated keys absent
    if sed.get("FIREWORKS_MODEL") and "FIREWORKS_MODEL_INGESTION" not in sed:
        sed.setdefault("FIREWORKS_MODEL_INGESTION", sed["FIREWORKS_MODEL"])
        sed.setdefault("FIREWORKS_MODEL_DEFAULT", sed["FIREWORKS_MODEL"])

    for key in KEYS:
        if key in existing and existing[key]:
            continue
        val = sed.get(key)
        if not val:
            continue
        to_add.append(f"{key}={val}")

    if not to_add:
        print("openrole/.env already has Fireworks keys — nothing to merge.")
        return 0

    block = "\n# --- Fireworks (merged from SED/.env) ---\n" + "\n".join(to_add) + "\n"
    OPENROLE_ENV.parent.mkdir(parents=True, exist_ok=True)
    if OPENROLE_ENV.is_file():
        OPENROLE_ENV.write_text(OPENROLE_ENV.read_text(encoding="utf-8").rstrip() + "\n" + block, encoding="utf-8")
    else:
        OPENROLE_ENV.write_text(
            "# Created by merge_fireworks_env.py — copy from .env.example for full config\n" + block,
            encoding="utf-8",
        )
    print(f"Added {len(to_add)} Fireworks variable(s) to {OPENROLE_ENV}")
    print("Re-run: python scripts/check_env.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
