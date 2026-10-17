import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config.settings import Settings
from app.main import create_app
from tests.support import ClientFactory, ensure_database_exists

DEFAULT_TEST_DATABASE_URL = "postgresql+psycopg://devbot:devbot@localhost:5432/dev_slack_bot_test"


@pytest.fixture(scope="session")
def test_database_url() -> str:
    database_url = os.environ.get("TEST_DATABASE_URL", DEFAULT_TEST_DATABASE_URL)
    ensure_database_exists(database_url)
    return database_url


@pytest.fixture
def client_for_database(tmp_path: Path) -> ClientFactory:
    def build(database_url: str) -> TestClient:
        return TestClient(create_app(Settings(database_url=database_url, frontend_dir=tmp_path)))

    return build


@pytest.fixture
def client(client_for_database: ClientFactory, test_database_url: str) -> TestClient:
    return client_for_database(test_database_url)
