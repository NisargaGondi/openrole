"""OpenAI chat models — re-export from compatible module."""

from openrole.llm.compatible import get_fireworks_chat_model, get_openai_chat_model

__all__ = ["get_openai_chat_model", "get_fireworks_chat_model"]
