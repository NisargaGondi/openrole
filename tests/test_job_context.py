"""Tests for job search context extraction."""

from openrole.agents.job_context import _heuristic_context
from openrole.db.models import Job, JobStatus
from openrole.schemas.job_context import JobSearchContext


def test_heuristic_extracts_cities_and_security_dept():
    job = Job(
        company_id="x",
        title="Senior Security Engineer",
        department=None,
        locations=[],
        description=(
            "Join Salesforce Red Team Security in San Jose, CA or Austin, TX. "
            "You will work on offensive security assessments."
        ),
        status=JobStatus.DISCOVERED,
    )
    ctx = _heuristic_context(job, JobSearchContext())
    assert any("San Jose" in loc for loc in ctx.office_locations)
    assert any("Austin" in loc for loc in ctx.office_locations)
    assert any("red team" in k.lower() or "security" in k.lower() for k in ctx.department_keywords)
