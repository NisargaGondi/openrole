"""Main LangGraph workflow."""

from langgraph.graph import END, START, StateGraph

from openrole.agents.job_ingestion import JobIngestionError, ingest_job
from openrole.graph.state import OpenRoleState


def _ingest_node(state: OpenRoleState) -> dict:
    errors: list[str] = list(state.get("errors") or [])
    try:
        result = ingest_job(
            job_url=state.get("job_url"),
            job_text=state.get("job_description_text"),
        )
        parsed = result.get("parsed_job") or {}
        return {
            "parsed_job": parsed,
            "job_id": result.get("job_id"),
            "company": {"id": result.get("company_id"), "name": parsed.get("company_name")},
            "errors": errors,
            "warnings": result.get("warnings") or [],
        }
    except JobIngestionError as exc:
        return {"errors": errors + [str(exc)]}
    except Exception as exc:
        return {"errors": errors + [f"Ingestion failed: {exc}"]}


def build_graph():
    graph = StateGraph(OpenRoleState)
    graph.add_node("ingest", _ingest_node)
    graph.add_edge(START, "ingest")
    graph.add_edge("ingest", END)
    return graph.compile()


def run_pipeline(*, job_url: str | None = None, job_text: str | None = None) -> dict:
    app = build_graph()
    initial: OpenRoleState = {}
    if job_url:
        initial["job_url"] = job_url
    if job_text:
        initial["job_description_text"] = job_text
    return app.invoke(initial)
