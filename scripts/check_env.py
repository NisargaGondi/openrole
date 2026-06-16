#!/usr/bin/env python3
"""Validate .env and optional LLM connectivity. Does not print secrets."""

from __future__ import annotations

import sys

from openrole.config import get_settings
from openrole.db.session import init_db


def main() -> int:
    settings = get_settings()
    issues: list[str] = []
    ok: list[str] = []

    ok.append(f"APP_ENV={settings.app_env}")
    ok.append(f"DATABASE_URL={settings.masked_database_url()}")

    if settings.resolved_llm_provider == "vertex":
        ok.append(f"Vertex AI ready (project={settings.gcp_project_id})")
    elif settings.vertex_configured:
        ok.append(f"GCP_PROJECT_ID set ({len(settings.gcp_project_id or '')} chars)")
        issues.append(
            "GOOGLE_APPLICATION_CREDENTIALS file not found — set path in .env or run "
            "`gcloud auth application-default login`"
        )
    elif settings.resolved_llm_provider == "fireworks":
        ok.append("Fireworks AI ready")
    elif settings.resolved_llm_provider in ("openrouter", "openai"):
        ok.append(f"OpenAI-compatible ready (provider={settings.resolved_llm_provider})")
    elif settings.llm_configured:
        ok.append(f"LLM provider={settings.resolved_llm_provider}")
    else:
        issues.append(settings.llm_configuration_hint().split("\n")[0])

    if settings.openai_configured:
        ok.append("OPENAI_API_KEY set")
    if settings.fireworks_configured:
        ok.append("FIREWORKS_API_KEY set")
    ok.append(f"LLM_PROVIDER choice={settings.llm_provider_choice} → active={settings.resolved_llm_provider}")

    if not settings.apollo_api_key:
        ok.append("APOLLO_API_KEY empty (OK until milestone 2–3)")
    else:
        ok.append("APOLLO_API_KEY set")

    try:
        init_db()
        ok.append("Database init OK")
    except Exception as exc:
        issues.append(f"Database init failed: {exc}")

    if settings.llm_configured:
        try:
            from openrole.llm import get_chat_model

            model = get_chat_model()
            reply = model.invoke("Reply with exactly: openrole-ok")
            text = getattr(reply, "content", str(reply))
            provider = settings.resolved_llm_provider
            model_name = settings.ingestion_model_name()
            ok.append(f"LLM ping OK ({provider}, model={model_name})")
            if "openrole" not in str(text).lower():
                ok.append(f"LLM reply snippet: {str(text)[:80]}...")
        except Exception as exc:
            issues.append(f"LLM call failed ({settings.llm_provider}): {exc}")

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
