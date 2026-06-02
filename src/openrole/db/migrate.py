"""CLI entrypoint: create database tables."""

from openrole.db.session import init_db


def main() -> None:
    init_db()
    print("Database tables created (or already exist).")


if __name__ == "__main__":
    main()
