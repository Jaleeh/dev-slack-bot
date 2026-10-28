from pathlib import Path

import pytest

from evals.ask import AskConfig, main

pytestmark = pytest.mark.usefixtures("offline_model")


@pytest.fixture
def config(sample_cache: Path) -> AskConfig:
    return AskConfig(cache_dir=sample_cache)


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
