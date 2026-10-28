import pytest
from langchain_ollama import ChatOllama

from evals.settings import EvalSettings, build_judge

ENV_VARS = ("CHAT_MODEL", "EVAL_JUDGE_MODEL", "OLLAMA_BASE_URL")


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def test_judge_copies_the_chat_model_when_unset() -> None:
    settings = EvalSettings(_env_file=None, chat_model="anthropic:x")

    assert settings.judge_model == "anthropic:x"


def test_judge_model_overrides_the_chat_model() -> None:
    settings = EvalSettings(_env_file=None, eval_judge_model="ollama:other:7b")

    assert settings.judge_model == "ollama:other:7b"


def test_ollama_judge_uses_the_configured_url() -> None:
    settings = EvalSettings(_env_file=None, ollama_base_url="http://ollama:1")

    judge = build_judge(settings)

    assert isinstance(judge, ChatOllama)
    assert judge.base_url == "http://ollama:1"
    assert judge.temperature == 0


def test_a_bad_agent_setting_does_not_stop_the_judge(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SEARCH_SKIP", "docs/")

    assert EvalSettings(_env_file=None).judge_model == "ollama:ornith:9b"


def test_ollama_judge_reads_as_much_context_as_the_agent_gathers() -> None:
    judge = build_judge(EvalSettings(_env_file=None))

    assert isinstance(judge, ChatOllama)
    assert judge.num_ctx == 32768
