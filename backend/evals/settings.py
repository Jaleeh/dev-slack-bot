"""Model settings for evals, kept apart from the app's settings so evals run without a database."""

from pathlib import Path

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT_ENV = Path(__file__).resolve().parents[2] / ".env"
JUDGE_TEMPERATURE = 0
OLLAMA_PREFIX = "ollama:"


class EvalSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_ROOT_ENV, extra="ignore")

    chat_model: str = "ollama:ornith:9b"
    eval_judge_model: str = ""
    ollama_base_url: str = "http://localhost:11434"

    @property
    def judge_model(self) -> str:
        return self.eval_judge_model or self.chat_model


def build_judge(settings: EvalSettings) -> BaseChatModel:
    model = settings.judge_model

    # Other providers read base_url as their own API address.
    if model.startswith(OLLAMA_PREFIX):
        return init_chat_model(
            model, temperature=JUDGE_TEMPERATURE, base_url=settings.ollama_base_url
        )

    return init_chat_model(model, temperature=JUDGE_TEMPERATURE)
