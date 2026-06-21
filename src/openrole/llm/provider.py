"""Route LLM calls to Vertex AI, Fireworks, OpenRouter, or OpenAI."""

from langchain_core.language_models import BaseChatModel

from openrole.config import get_settings


def get_chat_model(
    *,
    writing: bool = False,
    ingestion: bool = False,
    research: bool = False,
    fast: bool = False,
    temperature: float = 0.2,
) -> BaseChatModel:
    """Return a chat model for the active LLM_PROVIDER (or auto-detected fallback)."""
    settings = get_settings()
    provider = settings.resolved_llm_provider

    from openrole.llm.tracking import wrap_tracked

    if provider == "vertex":
        from openrole.llm.vertex import get_chat_model as get_vertex_chat_model

        inner = get_vertex_chat_model(
            writing=writing,
            ingestion=ingestion,
            research=research,
            fast=fast,
            temperature=temperature,
        )
    elif provider == "fireworks":
        from openrole.llm.compatible import get_fireworks_chat_model

        inner = get_fireworks_chat_model(
            writing=writing,
            ingestion=ingestion,
            research=research,
            fast=fast,
            temperature=temperature,
        )
    elif provider in ("openrouter", "openai"):
        from openrole.llm.compatible import get_openai_chat_model

        inner = get_openai_chat_model(
            writing=writing,
            ingestion=ingestion,
            research=research,
            fast=fast,
            temperature=temperature,
        )
    else:
        raise RuntimeError(settings.llm_configuration_hint())

    return wrap_tracked(
        inner,
        writing=writing,
        ingestion=ingestion,
        research=research,
        fast=fast,
    )
