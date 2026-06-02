"""Shared graph state schema (expanded as agents are implemented)."""

from typing import Annotated, Any, TypedDict

from langgraph.graph.message import add_messages


class OpenRoleState(TypedDict, total=False):
    """State passed between LangGraph nodes."""

    messages: Annotated[list, add_messages]
    job_url: str
    job_description_text: str
    job_id: str
    parsed_job: dict[str, Any]
    company: dict[str, Any]
    contacts: list[dict[str, Any]]
    outreach_drafts: list[dict[str, Any]]
    warnings: list[str]
    errors: list[str]
