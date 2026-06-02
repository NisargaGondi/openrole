#!/usr/bin/env python3
"""Validate .env and optional Vertex AI connectivity. Does not print secrets."""

from __future__ import annotations

import os
import sys

from openrole.config import get_settings
from openrole.db.session import init_db


def main() -> int:
    settings = get_settings()
    issues: list[str] = []
    ok: list[str] = []

    ok.append(f"APP_ENV={settings.app_env}")
    ok.append(f"DATABASE_URL={settings.masked_database_url()}")

    if settings.gcp_project_id:
        ok.append(f"GCP_PROJECT_ID set ({len(settings.gcp_project_id)} chars)")
    else:
        issues.append("GCP_PROJECT_ID is missing")

    if settings.gcp_credentials_ready:
        ok.append("GCP credentials path exists or ADC env is set")
    else:
        issues.append(
            "GOOGLE_APPLICATION_CREDENTIALS file not found — set path in .env or run "
            "`gcloud auth application-default login`"
        )

    if not settings.apollo_api_key:
        ok.append("APOLLO_API_KEY empty (OK until milestone 2–3)")
    else:
        ok.append("APOLLO_API_KEY set")

    try:
        init_db()
        ok.append("Database init OK")
    except Exception as exc:
        issues.append(f"Database init failed: {exc}")

    if settings.vertex_configured and settings.gcp_credentials_ready:
        try:
            from openrole.llm.vertex import get_chat_model

            model = get_chat_model()
            reply = model.invoke("Reply with exactly: openrole-ok")
            text = getattr(reply, "content", str(reply))
            ok.append(f"Vertex AI ping OK (model={settings.vertex_model_default})")
            if "openrole" not in str(text).lower():
                ok.append(f"Vertex reply snippet: {str(text)[:80]}...")
        except Exception as exc:
            issues.append(f"Vertex AI call failed: {exc}")

    print("OpenRole environment check\n")
    for line in ok:
        print(f"  OK  {line}")
    for line in issues:
        print(f"  !!  {line}")

    if issues:
        print("\nFix the items above before milestone 1.")
        return 1
    print("\nEnvironment looks good.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
