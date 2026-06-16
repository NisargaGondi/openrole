"""OpenAI-compatible chat backends: OpenAI, OpenRouter, Fireworks."""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI

from openrole.config import get_settings


def _chat_openai_compatible(
    *,
    api_key: str,
    api_base: str | None,
    model_name: str,
    temperature: float,
    openrouter_headers: bool = False,
) -> BaseChatModel:
    kwargs: dict = {
        "model": model_name,
        "api_key": api_key,
        "temperature": temperature,
    }
    if api_base:
        kwargs["base_url"] = api_base.rstrip("/")
    if openrouter_headers:
        kwargs["default_headers"] = {
            "HTTP-Referer": "https://github.com/NisargaGondi/openrole",
            "X-Title": "OpenRole",
        }
        kwargs.setdefault("model_kwargs", {})
        kwargs["model_kwargs"].setdefault(
            "extra_body",
            {"reasoning": {"effort": "none"}},
        )
    return ChatOpenAI(**kwargs)


def get_openai_chat_model(
    *,
    writing: bool = False,
    ingestion: bool = False,
    temperature: float = 0.2,
) -> BaseChatModel:
    settings = get_settings()
    if not settings.openai_api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Add it to .env before using OpenAI/OpenRouter."
        )
    if ingestion:
        model_name = settings.openai_model_ingestion
    elif writing:
        model_name = settings.openai_model_writing
    else:
        model_name = settings.openai_model_default
    model_name = settings.resolve_openai_model(model_name)
    return _chat_openai_compatible(
        api_key=settings.openai_api_key,
        api_base=settings.resolved_openai_api_base,
        model_name=model_name,
        temperature=temperature,
        openrouter_headers=settings.using_openrouter,
    )


def get_fireworks_chat_model(
    *,
    writing: bool = False,
    ingestion: bool = False,
    temperature: float = 0.2,
) -> BaseChatModel:
    settings = get_settings()
    if not settings.fireworks_api_key:
        raise RuntimeError(
            "FIREWORKS_API_KEY is not set. Copy from SummerRA/SED/.env or add to openrole/.env."
        )
    if ingestion:
        model_name = settings.fireworks_model_ingestion
    elif writing:
        model_name = settings.fireworks_model_writing
    else:
        model_name = settings.fireworks_model_default
    return _chat_openai_compatible(
        api_key=settings.fireworks_api_key,
        api_base=settings.fireworks_api_base,
        model_name=model_name,
        temperature=temperature,
    )
