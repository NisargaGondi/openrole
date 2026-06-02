"""Main LangGraph workflow — placeholder until agents are wired (milestone 5)."""

from langgraph.graph import END, START, StateGraph

from openrole.graph.state import OpenRoleState


def _stub_ingest(state: OpenRoleState) -> dict:
    return {"parsed_job": {"status": "not_implemented", "input": state.get("job_url") or "text"}}


def build_graph():
    graph = StateGraph(OpenRoleState)
    graph.add_node("ingest", _stub_ingest)
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
