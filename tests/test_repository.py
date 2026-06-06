"""Tests for repository contact listing and stale marking."""

import openrole.db.session as db_session
from openrole.config import get_settings
from openrole.db.models import Company, Contact
from openrole.db.repository import list_contacts_for_job, save_discovered_contacts
from openrole.db.session import init_db, session_scope
from openrole.schemas.contact import DiscoveredContact


def _setup():
    db_session._engine = None
    db_session._SessionLocal = None
    get_settings.cache_clear()
    init_db()


def test_list_contacts_for_job_scoped():
    _setup()
    with session_scope() as session:
        co = Company(name="Acme", domain="acme.com")
        session.add(co)
        session.flush()
        c1 = DiscoveredContact(full_name="Pat", metadata_json={"source_job_id": "job-a"})
        c2 = DiscoveredContact(full_name="Sam", metadata_json={"source_job_id": "job-b"})
        save_discovered_contacts(session, company_id=co.id, contacts=[c1], source_job_id="job-a")
        save_discovered_contacts(session, company_id=co.id, contacts=[c2], source_job_id="job-b")
        session.commit()
        scoped = list_contacts_for_job(session, company_id=co.id, source_job_id="job-a")
        assert len(scoped) == 1
        assert scoped[0].full_name == "Pat"
