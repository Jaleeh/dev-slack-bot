from collections.abc import Callable

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, make_url, text
from sqlalchemy.pool import NullPool

ClientFactory = Callable[[str], TestClient]

UNREACHABLE_DATABASE_URL = "postgresql+psycopg://x:y@localhost:1/none"
UNREACHABLE_URL = "http://localhost:9"


def ensure_database_exists(database_url: str) -> None:
    """Creates the test database on first use, so tests work on any existing Postgres volume."""
    url = make_url(database_url)
    if not url.database:
        raise ValueError(f"Test database URL needs a database name: {url!r}")

    maintenance = create_engine(
        url.set(database="postgres"), isolation_level="AUTOCOMMIT", poolclass=NullPool
    )

    with maintenance.connect() as connection:
        exists = connection.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": url.database}
        ).scalar()
        if not exists:
            connection.exec_driver_sql(f'CREATE DATABASE "{url.database}"')
