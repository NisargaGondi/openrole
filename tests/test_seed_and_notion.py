"""Tests for company seeding and Notion property mapping."""

from pathlib import Path

from openrole.config import Settings
from openrole.db.seed_companies import load_company_targets, seed_companies_from_file
from openrole.sync.notion import _page_properties


def test_load_scout_targets_yaml():
    path = Path(__file__).resolve().parents[1] / "data" / "scout_targets.yaml"
    companies = load_company_targets(path)
    assert len(companies) >= 25
    assert companies[0].get("name")
    assert companies[0].get("greenhouse_token") or companies[0].get("ashby_org")


def test_seed_companies_from_file(tmp_path):
    yaml_path = tmp_path / "targets.yaml"
    yaml_path.write_text(
        "companies:\n"
        "  - name: TestCo\n"
        "    domain: testco.com\n"
        "    greenhouse_token: testco\n",
        encoding="utf-8",
    )
    result = seed_companies_from_file(yaml_path)
    assert result["upserted"] == 1
    assert result["with_scout_metadata"] == 1


def test_notion_page_properties_custom_names():
    settings = Settings.model_construct(
        database_url="sqlite:///:memory:",
        notion_prop_title="Role",
        notion_prop_company="Employer",
        notion_prop_url="Link",
        notion_prop_score="Match",
        notion_prop_status="Stage",
        notion_prop_source="Source",
        notion_prop_opt="Visa",
    )
    props = _page_properties(
        {
            "title": "ML Engineer",
            "company": "Acme",
            "url": "https://example.com/job",
            "relevance_score": 72,
            "status": "discovered",
            "scout_source": "handshake",
            "opt_status": "eligible",
        },
        settings=settings,
    )
    assert "Role" in props
    assert props["Role"]["title"][0]["text"]["content"] == "ML Engineer"
    assert props["Employer"]["rich_text"][0]["text"]["content"] == "Acme"
    assert props["Link"]["url"] == "https://example.com/job"
    assert props["Match"]["number"] == 72.0
    assert props["Source"]["rich_text"][0]["text"]["content"] == "handshake"
    assert props["Visa"]["rich_text"][0]["text"]["content"] == "eligible"
