"""Track LLM calls by model name for usage/cost and Live Activity."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Iterator

from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import RunnableConfig

from openrole.config import get_settings

_llm_ctx: ContextVar[dict[str, Any]] = ContextVar("llm_usage_ctx", default={})

ROLE_LABELS = {
    "ingestion": "ingestion",
    "research": "research",
    "writing": "writing",
    "fast": "fast",
    "default": "default",
}


def short_model_name(full: str) -> str:
    """`accounts/fireworks/models/glm-5p2` → `glm-5p2`."""
    if not full:
        return "unknown"
    return full.rsplit("/", 1)[-1]


def resolve_llm_role(
    *,
    writing: bool = False,
    ingestion: bool = False,
    research: bool = False,
    fast: bool = False,
) -> tuple[str, str, str]:
    """Return (role_key, short_model_id, full_model_id)."""
    settings = get_settings()
    if ingestion:
        role = "ingestion"
        full = settings.ingestion_model_name()
    elif research:
        role = "research"
        full = settings.research_model_name()
    elif writing:
        role = "writing"
        full = settings.writing_model_name()
    elif fast:
        role = "fast"
        full = settings.fast_model_name()
    else:
        role = "default"
        full = settings.default_model_name()
    return role, short_model_name(full), full


def model_label_for_role(
    *,
    writing: bool = False,
    ingestion: bool = False,
    research: bool = False,
    fast: bool = False,
) -> str:
    return resolve_llm_role(
        writing=writing, ingestion=ingestion, research=research, fast=fast
    )[1]


def format_llm_activity(
    detail: str,
    *,
    writing: bool = False,
    ingestion: bool = False,
    research: bool = False,
    fast: bool = False,
) -> str:
    """Live Activity line: `[glm-5p2] ingestion · batch enrich · 6 jobs`."""
    role_key, model_id, _full = resolve_llm_role(
        writing=writing, ingestion=ingestion, research=research, fast=fast
    )
    role_label = ROLE_LABELS.get(role_key, role_key)
    return f"[{model_id}] {role_label} · {detail}"


def llm_service_key(model_id: str) -> str:
    return f"llm/{model_id}"


@contextmanager
def llm_usage_context(
    *,
    job_id: str | None = None,
    company: str | None = None,
    pipeline_step: str | None = None,
    detail: str | None = None,
    suppress_activity: bool = False,
    log_activity: bool = False,
) -> Iterator[None]:
    """Attach job/pipeline metadata to subsequent LLM invoke tracking."""
    token = _llm_ctx.set(
        {
            "job_id": job_id,
            "company": company,
            "pipeline_step": pipeline_step,
            "detail": detail,
            "suppress_activity": suppress_activity,
            "log_activity": log_activity,
        }
    )
    try:
        yield
    finally:
        _llm_ctx.reset(token)


def record_llm_call(
    *,
    model_id: str,
    role: str,
    detail: str | None = None,
    log_activity: bool = True,
) -> None:
    from openrole.api.usage_tracker import record_usage

    ctx = _llm_ctx.get()
    service = llm_service_key(model_id)
    role_label = ROLE_LABELS.get(role, role)
    merged_detail = detail or ctx.get("detail")
    record_usage(
        service=service,
        calls=1,
        job_id=ctx.get("job_id"),
        company=ctx.get("company"),
        pipeline_step=ctx.get("pipeline_step"),
        detail=merged_detail,
    )
    if not log_activity or ctx.get("suppress_activity"):
        return
    from openrole.api.activity_store import log as act_log

    msg = f"[{model_id}] {role_label}"
    if merged_detail:
        msg = f"{msg} · {merged_detail}"
    act_log(msg, icon="sparkles")


class TrackedChatModel:
    """Wrap a chat model to record each invoke by configured model id."""

    def __init__(self, inner: BaseChatModel, *, model_id: str, role: str) -> None:
        self._inner = inner
        self.model_id = model_id
        self.role = role

    def invoke(
        self,
        input: Any,
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> Any:
        self._track_invoke()
        return self._inner.invoke(input, config=config, **kwargs)

    async def ainvoke(
        self,
        input: Any,
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> Any:
        self._track_invoke()
        return await self._inner.ainvoke(input, config=config, **kwargs)

    def _track_invoke(self) -> None:
        ctx = _llm_ctx.get()
        record_llm_call(
            model_id=self.model_id,
            role=self.role,
            log_activity=bool(ctx.get("log_activity")),
        )

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


def wrap_tracked(
    model: BaseChatModel,
    *,
    writing: bool = False,
    ingestion: bool = False,
    research: bool = False,
    fast: bool = False,
) -> TrackedChatModel:
    role, short, _full = resolve_llm_role(
        writing=writing, ingestion=ingestion, research=research, fast=fast
    )
    return TrackedChatModel(inner=model, model_id=short, role=role)
