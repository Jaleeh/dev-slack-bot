import pytest
from langchain_ollama import ChatOllama
from pydantic import ValidationError
from pydantic_settings import SettingsError

from app.config.agent import AgentSettings, build_rewrite_model, build_search_model

ENV_VARS = (
    "CHAT_MODEL",
    "OLLAMA_BASE_URL",
    "AGENT_THINKING",
    "AGENT_MAX_TOOL_CALLS",
    "AGENT_MAX_TOKENS",
    "AGENT_CONTEXT_TOKENS",
    "RETRIEVAL",
    "SEARCH_SKIP",
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def test_retrieval_other_than_direct_is_refused() -> None:
    with pytest.raises(ValidationError, match="retrieval"):
        AgentSettings(_env_file=None, retrieval="vector")


def test_search_skip_reads_a_json_list_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SEARCH_SKIP", '["docs/"]')

    assert AgentSettings(_env_file=None).search_skip == ("docs/",)


def test_search_skip_that_is_not_json_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SEARCH_SKIP", "docs/")

    with pytest.raises(SettingsError, match="search_skip"):
        AgentSettings(_env_file=None)


def test_search_model_thinks_and_uses_the_context_size() -> None:
    model = build_search_model(AgentSettings(_env_file=None))

    assert isinstance(model, ChatOllama)
    assert model.reasoning is True
    assert model.num_ctx == 32768
    assert model.temperature == 0


def test_rewrite_model_does_not_think() -> None:
    model = build_rewrite_model(AgentSettings(_env_file=None))

    assert isinstance(model, ChatOllama)
    assert model.reasoning is False
