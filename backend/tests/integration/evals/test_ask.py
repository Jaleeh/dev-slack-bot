from pathlib import Path

import pytest

from evals.ask import AskConfig, main
from tests.support import UNREACHABLE_URL


@pytest.fixture
def config(tmp_path: Path) -> AskConfig:
    """A cache that already holds the sample repo, so no test needs the network."""
    clone = tmp_path / "django-oscar@4.2.1"
    clone.mkdir()
    (clone / "README.md").write_text("Oscar\n")

    return AskConfig(cache_dir=tmp_path)


@pytest.fixture(autouse=True)
def offline_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHAT_MODEL", "ollama:ornith:9b")
    monkeypatch.setenv("OLLAMA_BASE_URL", UNREACHABLE_URL)
    monkeypatch.delenv("RETRIEVAL", raising=False)
    monkeypatch.delenv("SEARCH_SKIP", raising=False)


def test_ask_stops_when_retrieval_is_not_direct(
    config: AskConfig, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("RETRIEVAL", "vector")

    assert main("Why?", config) == 1

    stderr = capsys.readouterr().err
    assert "ask stopped:" in stderr
    assert "retrieval" in stderr


def test_ask_stops_when_search_skip_is_not_json(
    config: AskConfig, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("SEARCH_SKIP", "docs/")

    assert main("Why?", config) == 1

    assert "search_skip" in capsys.readouterr().err


def test_ask_stops_cleanly_when_ollama_is_unreachable(
    config: AskConfig, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main("Why?", config) == 1

    assert "connection to Ollama" in capsys.readouterr().err


def test_ask_needs_a_question(config: AskConfig, capsys: pytest.CaptureFixture[str]) -> None:
    assert main("  ", config) == 1

    assert 'make ask Q="' in capsys.readouterr().err
