"""Tests for CSV tracker upsert."""

from openrole.sync.sheets import _row_key, upsert_tracker_rows_to_csv


def test_row_key_prefers_job_id():
    assert _row_key({"job_id": "abc", "url": "http://x"}) == "id:abc"


def test_csv_upsert_no_duplicates(tmp_path):
    path = tmp_path / "tracker.csv"
    row_a = {
        "job_id": "1",
        "title": "Engineer",
        "company": "Acme",
        "url": "https://a.com/1",
        "platform": "indeed",
        "status": "discovered",
        "relevance_score": "50",
        "scout_source": "jobspy",
        "search_term": "ml",
        "run_id": "r1",
        "discovered_at": "t1",
    }
    upsert_tracker_rows_to_csv([row_a], path=path)
    row_b = dict(row_a)
    row_b["status"] = "applied"
    row_b["relevance_score"] = "55"
    upsert_tracker_rows_to_csv([row_b], path=path)

    text = path.read_text(encoding="utf-8")
    assert text.count("https://a.com/1") == 1
    assert "applied" in text
