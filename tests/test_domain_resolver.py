"""Tests for domain resolution."""

from unittest.mock import patch

from openrole.tools.domain_resolver import (
    DomainResolution,
    _is_plausible_domain,
    enrich_parsed_job_domain,
    resolve_company_domain,
)
from openrole.schemas.job import ParsedJob


def test_plausible_domain_rejects_job_boards():
    assert not _is_plausible_domain("greenhouse.io")
    assert _is_plausible_domain("crowdstrike.com")


def test_resolve_from_source_url():
    r = resolve_company_domain(
        company_name="CrowdStrike",
        source_url="https://careers.crowdstrike.com/jobs/123",
    )
    assert r is not None
    assert r.domain == "careers.crowdstrike.com"


@patch("openrole.tools.domain_resolver.apollo_client.search_organization")
def test_resolve_via_apollo(mock_search):
    mock_search.return_value = {"primary_domain": "acme.com", "name": "Acme Corp"}
    r = resolve_company_domain(company_name="Acme Corp")
    assert r == DomainResolution("acme.com", "apollo", "inferred")


def test_enrich_parsed_job_domain():
    parsed = ParsedJob(title="Eng", company_name="Acme", company_domain="acme.com")
    out, warnings = enrich_parsed_job_domain(parsed)
    assert out.company_domain == "acme.com"
    assert not warnings
