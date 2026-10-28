"""Model settings for evals, kept apart from the app's settings so evals run without a database."""

from langchain_core.language_models import BaseChatModel
from pydantic import ValidationError
from pydantic_settings import SettingsError

from app.config.agent import MODEL_TEMPERATURE, ModelSettings, build_chat_model

JUDGE_TEMPERATURE = MODEL_TEMPERATURE
# The agent's default context, so the code under a faithfulness check isn't silently cut.
JUDGE_CONTEXT_TOKENS = 32768


class EvalSettings(ModelSettings):
    eval_judge_model: str = ""

    @property
    def judge_model(self) -> str:
        return self.eval_judge_model or self.chat_model


def build_judge(settings: EvalSettings) -> BaseChatModel:
    return build_chat_model(
        settings.judge_model, settings.ollama_base_url, num_ctx=JUDGE_CONTEXT_TOKENS
    )


def describe_settings_error(error: ValidationError | SettingsError) -> str:
    if isinstance(error, SettingsError):
        return str(error)

    return "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in error.errors())
