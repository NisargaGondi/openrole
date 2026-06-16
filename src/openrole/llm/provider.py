"""Route LLM calls to Vertex AI, Fireworks, OpenRouter, or OpenAI."""

from langchain_core.language_models import BaseChatModel

from openrole.config import get_settings


def get_chat_model(
    *,
    writing: bool = False,
    ingestion: bool = False,
    temperature: float = 0.2,
) -> BaseChatModel:
    """Return a chat model for the active LLM_PROVIDER (or auto-detected fallback)."""
    settings = get_settings()
    provider = settings.resolved_llm_provider

    if provider == "vertex":
        from openrole.llm.vertex import get_chat_model as get_vertex_chat_model

        return get_vertex_chat_model(
            writing=writing, ingestion=ingestion, temperature=temperature
        )
    if provider == "fireworks":
        from openrole.llm.compatible import get_fireworks_chat_model

        return get_fireworks_chat_model(
            writing=writing, ingestion=ingestion, temperature=temperature
        )
    if provider in ("openrouter", "openai"):
        from openrole.llm.compatible import get_openai_chat_model

        return get_openai_chat_model(
            writing=writing, ingestion=ingestion, temperature=temperature
        )
    raise RuntimeError(settings.llm_configuration_hint())
