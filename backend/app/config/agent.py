"""Model and agent settings, kept apart from the app's settings so they need no database."""

from pathlib import Path
from typing import Any, Literal

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel
from pydantic import PositiveInt
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.retrieval.direct.scope import DEFAULT_SKIP

REPO_ROOT_ENV = Path(__file__).resolve().parents[3] / ".env"
OLLAMA_PREFIX = "ollama:"
MODEL_TEMPERATURE = 0


class ModelSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_ROOT_ENV, extra="ignore")

    chat_model: str = "ollama:ornith:9b"
    ollama_base_url: str = "http://localhost:11434"


class AgentSettings(ModelSettings):
    agent_thinking: bool = True
    agent_max_tool_calls: PositiveInt = 15
    agent_max_tokens: PositiveInt = 1_000_000
    agent_context_tokens: PositiveInt = 32768
    retrieval: Literal["direct"] = "direct"
    search_skip: tuple[str, ...] = DEFAULT_SKIP


def build_search_model(settings: AgentSettings) -> BaseChatModel:
    return build_chat_model(
        settings.chat_model,
        settings.ollama_base_url,
        num_ctx=settings.agent_context_tokens,
        reasoning=settings.agent_thinking,
    )


def build_rewrite_model(settings: AgentSettings) -> BaseChatModel:
    return build_chat_model(
        settings.chat_model,
        settings.ollama_base_url,
        num_ctx=settings.agent_context_tokens,
        reasoning=False,
    )


def build_chat_model(model: str, ollama_base_url: str, **ollama_options: Any) -> BaseChatModel:
    """A chat model at temperature 0; `ollama_options` reach only Ollama models."""
    # Other providers read these keywords differently or not at all.
    if model.startswith(OLLAMA_PREFIX):
        ollama: BaseChatModel = init_chat_model(
            model, temperature=MODEL_TEMPERATURE, base_url=ollama_base_url, **ollama_options
        )
        return ollama

    return init_chat_model(model, temperature=MODEL_TEMPERATURE)
