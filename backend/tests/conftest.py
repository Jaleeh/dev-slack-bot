import os
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config.settings import Settings
from app.main import create_app
from tests.support import ClientFactory, ensure_database_exists

OLLAMA_REACHABILITY_TIMEOUT_SECONDS = 1
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


@pytest.fixture(scope="session")
def ollama_url() -> str:
    """The configured Ollama URL; skips the test when nothing answers there."""
    # Imported here so test runs that never touch a model don't load LangChain.
    from evals.settings import EvalSettings

    url = EvalSettings().ollama_base_url
    try:
        httpx.get(url, timeout=OLLAMA_REACHABILITY_TIMEOUT_SECONDS)
    except httpx.HTTPError:
        pytest.skip(f"Ollama not reachable at {url}")

    return url


@pytest.fixture(scope="session")
def ollama_judge(ollama_url: str) -> str:
    """The configured judge model; skips the test unless Ollama has it pulled."""
    from evals.settings import EvalSettings

    return require_pulled(EvalSettings().judge_model, ollama_url)


@pytest.fixture(scope="session")
def ollama_chat_model(ollama_url: str) -> str:
    """The configured chat model's Ollama name; skips the test unless Ollama has it pulled."""
    from app.config.agent import OLLAMA_PREFIX
    from evals.settings import EvalSettings

    return require_pulled(EvalSettings().chat_model, ollama_url).removeprefix(OLLAMA_PREFIX)


def require_pulled(model: str, ollama_url: str) -> str:
    from app.config.agent import OLLAMA_PREFIX

    if not model.startswith(OLLAMA_PREFIX):
        pytest.skip(f"model {model} is not an Ollama model")

    name = model.removeprefix(OLLAMA_PREFIX)
    pulled = {entry["name"] for entry in httpx.get(f"{ollama_url}/api/tags").json()["models"]}
    if not {name, f"{name}:latest"} & pulled:
        pytest.skip(f"{name} is not pulled; run: ollama pull {name}")

    return model


@pytest.fixture(scope="session")
def grammars() -> None:
    """Downloads the Python and TypeScript grammars; skips the test when that fails."""
    from tree_sitter_language_pack import DownloadError, download

    try:
        download(["python", "typescript"])
    except DownloadError as error:
        pytest.skip(f"tree-sitter grammars unavailable: {error}")
