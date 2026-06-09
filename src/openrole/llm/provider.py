"""Route LLM calls to Vertex AI (preferred) or OpenAI (fallback)."""

from langchain_core.language_models import BaseChatModel

from openrole.config import get_settings


def get_chat_model(
    *,
    writing: bool = False,
    ingestion: bool = False,
    temperature: float = 0.2,
) -> BaseChatModel:
    """Return a chat model using Vertex AI when configured, otherwise OpenAI."""
    settings = get_settings()
    if settings.vertex_ready:
        from openrole.llm.vertex import get_chat_model as get_vertex_chat_model

        return get_vertex_chat_model(
            writing=writing, ingestion=ingestion, temperature=temperature
        )
    if settings.openai_configured:
        from openrole.llm.openai_client import get_openai_chat_model

        return get_openai_chat_model(
            writing=writing, ingestion=ingestion, temperature=temperature
        )
    raise RuntimeError(
        "No LLM configured. Set GCP_PROJECT_ID + Google credentials for Vertex AI, "
        "or set OPENAI_API_KEY for OpenAI."
    )
