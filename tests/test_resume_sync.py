"""Tests for resume sync from .env."""

from unittest.mock import patch

import openrole.db.session as db_session
from openrole.config import clear_settings_cache, get_settings
from openrole.db.repository import list_resumes, sync_resumes_from_env
from openrole.db.session import init_db, session_scope


def test_sync_resumes_replaces_stale_rows(tmp_path, monkeypatch):
    db = tmp_path / "resumes.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")
    db_session._engine = None
    db_session._SessionLocal = None

    r1 = tmp_path / "old.md"
    r2 = tmp_path / "new_a.md"
    r3 = tmp_path / "new_b.md"

    init_db()
    with patch("openrole.tools.candidate_profile.load_candidate_profile") as mock_profile:
        mock_profile.return_value = {
            "resumes": [{"label": "old.md", "path": str(r1), "text": "old resume"}]
        }
        with session_scope() as session:
            assert len(sync_resumes_from_env(session)) == 1

        mock_profile.return_value = {
            "resumes": [
                {"label": "new_a.md", "path": str(r2), "text": "a"},
                {"label": "new_b.md", "path": str(r3), "text": "b"},
            ]
        }
        with session_scope() as session:
            synced = list_resumes(session)
            paths = {row.file_path for row in synced}
            assert len(synced) == 2
            assert str(r1) not in paths
            assert synced[0].is_default


def test_directory_expands_to_pdfs(tmp_path, monkeypatch):
    folder = tmp_path / "resumes"
    folder.mkdir()
    (folder / "a.pdf").write_text("not real pdf", encoding="utf-8")
    (folder / "b.pdf").write_text("not real pdf", encoding="utf-8")

    clear_settings_cache()
    monkeypatch.setenv("CANDIDATE_RESUME_PATHS", str(folder))
    paths = get_settings().candidate_resume_paths_list()
    assert len(paths) == 2
    assert all(p.suffix == ".pdf" for p in paths)
