"""Vertex AI Gemini chat models for LangGraph nodes."""

from langchain_core.language_models import BaseChatModel
from langchain_google_genai import ChatGoogleGenerativeAI

from openrole.config import get_settings


def get_chat_model(
    *,
    writing: bool = False,
    ingestion: bool = False,
    temperature: float = 0.2,
) -> BaseChatModel:
    settings = get_settings()
    if not settings.gcp_project_id:
        raise RuntimeError(
            "GCP_PROJECT_ID is not set. Add it to .env or export it before using Gemini."
        )
    if ingestion:
        model_name = settings.vertex_model_ingestion
    elif writing:
        model_name = settings.vertex_model_writing
    else:
        model_name = settings.vertex_model_default
    return ChatGoogleGenerativeAI(
        model=model_name,
        project=settings.gcp_project_id,
        location=settings.gcp_location,
        vertexai=True,
        temperature=temperature,
    )
