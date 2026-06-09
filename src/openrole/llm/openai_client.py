"""OpenAI chat models for LangGraph nodes (fallback when Vertex AI is unavailable)."""

from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI

from openrole.config import get_settings


def get_openai_chat_model(
    *,
    writing: bool = False,
    ingestion: bool = False,
    temperature: float = 0.2,
) -> BaseChatModel:
    settings = get_settings()
    if not settings.openai_api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Add it to .env before using OpenAI models."
        )
    if ingestion:
        model_name = settings.openai_model_ingestion
    elif writing:
        model_name = settings.openai_model_writing
    else:
        model_name = settings.openai_model_default
    model_name = settings.resolve_openai_model(model_name)

    kwargs: dict = {
        "model": model_name,
        "api_key": settings.openai_api_key,
        "temperature": temperature,
    }
    api_base = settings.resolved_openai_api_base
    if api_base:
        kwargs["base_url"] = api_base
        if settings.using_openrouter:
            kwargs["default_headers"] = {
                "HTTP-Referer": "https://github.com/NisargaGondi/openrole",
                "X-Title": "OpenRole",
            }
            # Prefer direct answers over long reasoning traces for JSON extraction tasks.
            kwargs.setdefault("model_kwargs", {})
            kwargs["model_kwargs"].setdefault(
                "extra_body",
                {"reasoning": {"effort": "none"}},
            )
    return ChatOpenAI(**kwargs)
