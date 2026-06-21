#!/usr/bin/env python3
"""Remove test placeholder companies (Acme, etc.) leaked from unit tests."""

from __future__ import annotations

from openrole.db.repository import delete_junk_scout_companies
from openrole.db.session import session_scope


def main() -> None:
    with session_scope() as session:
        result = delete_junk_scout_companies(session)
    print("Removed test companies:", result)


if __name__ == "__main__":
    main()
