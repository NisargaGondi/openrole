#!/usr/bin/env python3
"""Create database tables. Run from repo root after `pip install -e .`."""

from openrole.db.migrate import main

if __name__ == "__main__":
    main()
