"""Runs the agent on the question set and scores retrieval and answers from that one run."""

import os
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx
import ollama
import yaml
from langchain_core.language_models import BaseChatModel
from pydantic import AwareDatetime, BaseModel, ConfigDict, ValidationError, computed_field
from pydantic_settings import SettingsError

from app.agent.graph import Agent, build_agent
from app.config.agent import AgentSettings
from evals.agent_scores import (
    AgentMetrics,
    Attempt,
    QuestionScore,
    UnknownQuestions,
    agent_metrics,
    evidence,
    judged_checks,
    score,
    select_questions,
)
from evals.dataset_file import InvalidDataset
from evals.question_set import QUESTIONS_PATH, Question, load_question_set
from evals.run_record import (
    EVALS_DIR,
    TIMESTAMP_FORMAT,
    RepoCommitError,
    format_rows,
    git_commit,
    stop,
    write_record,
)
from evals.sample_repo import SampleRepoError, fetch_sample_repo, sample_repo_for
from evals.settings import EvalSettings, build_judge, describe_settings_error

COMMAND = "eval-agent"
IDS_ENV = "IDS"


class AgentRunConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    questions_path: Path = QUESTIONS_PATH
    cache_dir: Path = EVALS_DIR / ".cache"
    results_dir: Path = EVALS_DIR / "results"


DEFAULT_CONFIG = AgentRunConfig()


class RunSetup(BaseModel):
    model_config = ConfigDict(frozen=True)

    started_at: AwareDatetime
    git_commit: str
    dataset_version: int
    repo: str
    ref: str
    ids: tuple[str, ...]
    agent: AgentSettings
    judge_model: str


class AgentRun(BaseModel):
    model_config = ConfigDict(frozen=True)

    setup: RunSetup
    questions: tuple[QuestionScore, ...]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def metrics(self) -> AgentMetrics:
        return agent_metrics(self.questions)


@dataclass(frozen=True)
class RunRequest:
    ids: tuple[str, ...]
    agent: AgentSettings
    judge_model: str


@dataclass(frozen=True)
class Harness:
    agent: Agent
    judge: BaseChatModel


@dataclass(frozen=True)
class AgentRunPlan:
    setup: RunSetup
    questions: tuple[Question, ...]
    repo: Path
    path: Path


def main(ids: Sequence[str], config: AgentRunConfig = DEFAULT_CONFIG) -> int:
    """Runs and scores the named questions, or all of them; returns the process exit code."""
    try:
        settings = AgentSettings()
        eval_settings = EvalSettings()
    except (ValidationError, SettingsError) as error:
        return stop(COMMAND, f"bad setting: {describe_settings_error(error)}")

    try:
        judge = build_judge(eval_settings)
    except (ValueError, ImportError) as error:
        return stop(COMMAND, f"could not set up the judge {eval_settings.judge_model} ({error})")

    request = RunRequest(tuple(ids), settings, eval_settings.judge_model)
    try:
        plan = prepare(config, request)
    except (
        InvalidDataset,
        yaml.YAMLError,
        UnknownQuestions,
        SampleRepoError,
        RepoCommitError,
    ) as error:
        return stop(COMMAND, error)

    try:
        run = evaluate_agent(plan, Harness(build_agent(settings, plan.repo), judge))
    except httpx.TransportError as error:
        reason = f"connection to Ollama at {settings.ollama_base_url} failed ({error})"
        return stop(COMMAND, reason + kept_note(plan.path))
    except ollama.ResponseError as error:
        return stop(COMMAND, f"Ollama could not run a model ({error})" + kept_note(plan.path))

    print(format_summary(run, plan.path))
    return 0


def prepare(config: AgentRunConfig, request: RunRequest) -> AgentRunPlan:
    """Checks the questions and fetches the repo, so a bad id or fetch costs no model call."""
    started_at = datetime.now(UTC)
    question_set = load_question_set(config.questions_path)
    questions = select_questions(question_set, request.ids)
    clone = fetch_sample_repo(sample_repo_for(question_set), config.cache_dir)

    setup = RunSetup(
        started_at=started_at,
        git_commit=git_commit(),
        dataset_version=question_set.version,
        repo=question_set.repo,
        ref=question_set.ref,
        ids=request.ids,
        agent=request.agent,
        judge_model=request.judge_model,
    )
    path = config.results_dir / f"agent-{started_at:{TIMESTAMP_FORMAT}}.json"

    return AgentRunPlan(setup=setup, questions=questions, repo=clone, path=path)


def evaluate_agent(plan: AgentRunPlan, harness: Harness) -> AgentRun:
    """Rewrites the results file after each question, so a run that dies keeps what it finished."""
    run = AgentRun(setup=plan.setup, questions=())
    total = len(plan.questions)

    for number, question in enumerate(plan.questions, start=1):
        scored = run_question(question, harness)
        run = AgentRun(setup=plan.setup, questions=(*run.questions, scored))
        print(f"[{number}/{total}] {describe(scored)}", file=sys.stderr, flush=True)
        write_record(run, plan.path)

    return run


def run_question(question: Question, harness: Harness) -> QuestionScore:
    result = harness.agent.ask(question.question)
    attempt = Attempt(result=result, checks=(), evidence=evidence(result.tool_calls))
    unjudged = score(question, attempt)

    return unjudged.model_copy(update={"checks": judged_checks(harness.judge, question, unjudged)})


def describe(scored: QuestionScore) -> str:
    stats = f"{len(scored.tool_calls)} calls, {scored.seconds:.0f} s"
    if scored.is_empty:
        return f"{scored.id}: recall@5 {scored.recall_at_5:.2f}, empty, {stats}"

    return (
        f"{scored.id}: recall@5 {scored.recall_at_5:.2f}, facts {scored.fact_score:.2f}, "
        f"faithfulness {scored.faithfulness}, {stats}"
    )


def kept_note(path: Path) -> str:
    if not path.exists():
        return ""

    return f"; finished questions are in {path}, rerun the rest with {IDS_ENV}="


def format_summary(run: AgentRun, path: Path) -> str:
    metrics = run.metrics
    faithfulness = metrics.faithfulness

    return format_rows(
        [
            ("questions", str(len(run.questions))),
            ("recall@5", f"{metrics.recall_at_5:.3f}"),
            ("recall@10", f"{metrics.recall_at_10:.3f}"),
            ("MRR", f"{metrics.mrr:.3f}"),
            ("fact score", f"{metrics.fact_score:.3f}"),
            ("all facts stated", str(metrics.all_facts_stated)),
            (
                "faithfulness",
                f"{faithfulness.passed} pass, {faithfulness.failed} fail, "
                f"{faithfulness.unclear} unclear, {faithfulness.ungraded} ungraded",
            ),
            ("inconclusive", str(metrics.inconclusive)),
            ("empty", str(metrics.empty)),
            ("seconds", f"{metrics.seconds_total:.0f} total, {metrics.seconds_mean:.0f} mean"),
            ("tokens", f"{metrics.tokens_total} total, {metrics.tokens_mean:.0f} mean"),
            ("results", str(path)),
        ]
    )


if __name__ == "__main__":
    sys.exit(main(os.environ.get(IDS_ENV, "").split()))
