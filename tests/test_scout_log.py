"""Tests for scout run log."""

import json

from openrole.scheduler.scout_log import append_scout_run, last_scout_run, load_scout_runs


def test_append_and_load_scout_runs(tmp_path, monkeypatch):
    log_path = tmp_path / "scout_run_log.json"
    monkeypatch.setattr("openrole.scheduler.scout_log._LOG_PATH", log_path)

    append_scout_run({"run_id": "a", "ingested_new": 2}, trigger="manual")
    append_scout_run({"run_id": "b", "ingested_new": 1}, trigger="scheduled")

    rows = load_scout_runs(limit=5)
    assert len(rows) == 2
    assert rows[0]["run_id"] == "b"
    assert rows[0]["trigger"] == "scheduled"
    assert last_scout_run()["run_id"] == "b"
    assert json.loads(log_path.read_text())
