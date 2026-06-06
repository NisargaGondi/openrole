"""Ingest node."""

from __future__ import annotations

from openrole.agents.job_ingestion import JobIngestionError, ingest_job
from openrole.graph.state import OpenRoleState


def ingest_node(state: OpenRoleState) -> dict:
    if state.get("job_id"):
        return {"pipeline_stage": "ingest_skipped", "stages_completed": ["ingest_skipped"]}

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
            "pipeline_stage": "ingested",
            "stages_completed": ["ingest"],
            "warnings": result.get("warnings") or [],
        }
    except JobIngestionError as exc:
        return {"errors": [str(exc)], "pipeline_stage": "ingest_failed"}
    except Exception as exc:
        return {"errors": [f"Ingestion failed: {exc}"], "pipeline_stage": "ingest_failed"}
