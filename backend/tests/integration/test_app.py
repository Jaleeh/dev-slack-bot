from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config.settings import Settings
from app.main import CONTENT_SECURITY_POLICY, create_app
from tests.support import UNREACHABLE_DATABASE_URL, ClientFactory

INDEX_HTML = "<h1>status</h1>"


@pytest.fixture
def frontend_client(client_for_database: ClientFactory, tmp_path: Path) -> TestClient:
    (tmp_path / "index.html").write_text(INDEX_HTML)
    return client_for_database(UNREACHABLE_DATABASE_URL)


def test_root_serves_the_frontend_index(frontend_client: TestClient) -> None:
    response = frontend_client.get("/")

    assert response.status_code == 200
    assert INDEX_HTML in response.text


def test_unknown_api_path_returns_json_404_not_the_frontend(
    frontend_client: TestClient,
) -> None:
    response = frontend_client.get("/api/does-not-exist")

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")


def test_responses_carry_security_headers(frontend_client: TestClient) -> None:
    headers = frontend_client.get("/api/health").headers

    assert headers["x-content-type-options"] == "nosniff"
    assert headers["x-frame-options"] == "DENY"
    assert headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert headers["content-security-policy"] == CONTENT_SECURITY_POLICY


def test_app_starts_without_a_built_frontend(tmp_path: Path) -> None:
    settings = Settings(database_url=UNREACHABLE_DATABASE_URL, frontend_dir=tmp_path / "missing")

    client = TestClient(create_app(settings))

    assert client.get("/api/does-not-exist").status_code == 404
