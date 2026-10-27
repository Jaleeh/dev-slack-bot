"""Answers one question about the sample repository with the agent, showing its work."""

import os
import sys
from collections.abc import Callable
from itertools import count
from pathlib import Path

import httpx
import ollama
import yaml
from pydantic import BaseModel, ConfigDict, ValidationError
from pydantic_settings import SettingsError

from app.agent.graph import AgentResult, ToolCallRecord, build_agent
from app.config.agent import AgentSettings
from evals.dataset_file import InvalidDataset
from evals.question_set import QUESTIONS_PATH, load_question_set
from evals.run_record import EVALS_DIR, format_rows, stop
from evals.sample_repo import SampleRepoError, fetch_sample_repo, sample_repo_for

COMMAND = "ask"
QUESTION_ENV = "Q"


class AskConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    questions_path: Path = QUESTIONS_PATH
    cache_dir: Path = EVALS_DIR / ".cache"


DEFAULT_CONFIG = AskConfig()


def main(question: str, config: AskConfig = DEFAULT_CONFIG) -> int:
    """Prints each tool call, then the draft, the answer and the stats; returns the exit code."""
    if not question.strip():
        return stop(COMMAND, 'give a question: make ask Q="..."')

    try:
        settings = AgentSettings()
    except (ValidationError, SettingsError) as error:
        return stop(COMMAND, f"bad setting: {describe_settings_error(error)}")

    try:
        question_set = load_question_set(config.questions_path)
        clone = fetch_sample_repo(sample_repo_for(question_set), config.cache_dir)
    except (InvalidDataset, yaml.YAMLError, SampleRepoError) as error:
        return stop(COMMAND, error)

    try:
        result = build_agent(settings, clone).ask(question.strip(), on_call=call_printer())
    except httpx.TransportError as error:
        return stop(COMMAND, f"connection to Ollama at {settings.ollama_base_url} failed ({error})")
    except ollama.ResponseError as error:
        return stop(COMMAND, f"Ollama could not run {settings.chat_model} ({error})")

    print(format_result(result))
    return 0


def describe_settings_error(error: ValidationError | SettingsError) -> str:
    if isinstance(error, SettingsError):
        return str(error)

    return "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in error.errors())


def call_printer() -> Callable[[ToolCallRecord], None]:
    numbers = count(1)

    def print_call(record: ToolCallRecord) -> None:
        print(f"  [{next(numbers)}] {describe_call(record)}", flush=True)

    return print_call


def describe_call(record: ToolCallRecord) -> str:
    args = ", ".join(f"{name}={value!r}" for name, value in record.args.items())

    return f"{record.name}({args}) {record.outcome.value}"


def format_result(result: AgentResult) -> str:
    prompt_tokens = ", ".join(str(call.prompt_tokens) for call in result.model_calls)
    stats = format_rows(
        [
            ("tool calls", str(len(result.tool_calls))),
            ("tokens", str(result.tokens)),
            ("seconds", f"{result.seconds:.0f}"),
            ("stopped by", result.stop.value),
            ("empty", "yes" if result.is_empty else "no"),
            ("prompt tokens per call", prompt_tokens),
        ]
    )

    return f"\nDRAFT\n{result.draft or '(none)'}\n\nANSWER\n{result.answer}\n\n{stats}"


if __name__ == "__main__":
    sys.exit(main(os.environ.get(QUESTION_ENV, "")))
