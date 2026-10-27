"""Model settings for evals, kept apart from the app's settings so evals run without a database."""

from langchain_core.language_models import BaseChatModel

from app.config.agent import MODEL_TEMPERATURE, ModelSettings, build_chat_model

JUDGE_TEMPERATURE = MODEL_TEMPERATURE


class EvalSettings(ModelSettings):
    eval_judge_model: str = ""

    @property
    def judge_model(self) -> str:
        return self.eval_judge_model or self.chat_model


def build_judge(settings: EvalSettings) -> BaseChatModel:
    return build_chat_model(settings.judge_model, settings.ollama_base_url)
