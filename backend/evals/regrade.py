"""Judges a saved eval-agent run again, several times, without running the agent."""

import os
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from statistics import fmean
from typing import Any

import httpx
import ollama
import yaml
from langchain_core.language_models import BaseChatModel
from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    ValidationError,
    computed_field,
    field_serializer,
)
from pydantic_settings import SettingsError

from app.agent.graph import Toolbox
from app.agent.guardrails import Call, Outcome
from app.retrieval.direct.scope import open_scope
from app.retrieval.direct.search import DirectSearch
from evals.agent_runner import DEFAULT_CONFIG, AgentRun, AgentRunConfig, RunSetup
from evals.agent_scores import (
    AgentMetrics,
    QuestionScore,
    UnknownQuestions,
    agent_metrics,
    evidence,
    judged_checks,
    select_questions,
)
from evals.dataset_file import InvalidDataset
from evals.grader import CheckResult
from evals.question_set import Question, QuestionSet, load_question_set
from evals.run_record import (
    TIMESTAMP_FORMAT,
    RepoCommitError,
    format_rows,
    git_commit,
    stop,
    write_record,
)
from evals.sample_repo import SampleRepoError, fetch_sample_repo, sample_repo_for
from evals.settings import EvalSettings, build_judge, describe_settings_error

COMMAND = "regrade"
RUN_ENV = "RUN"
REPS_ENV = "REPS"
DEFAULT_REPS = "5"


class EvidenceMismatch(ValueError):
    def __init__(self, mismatches: Sequence[tuple[str, int, int]]) -> None:
        described = ", ".join(
            f"{id_} ({recorded} chars recorded, {replayed} replayed)"
            for id_, recorded, replayed in mismatches
        )
        super().__init__(f"replayed evidence differs from the run for {described}")
        self.ids = tuple(id_ for id_, _, _ in mismatches)


class NotAnAgentRun(ValueError):
    def __init__(self, path: Path) -> None:
        super().__init__(f"{path} is not an eval-agent results file")


class ChangedJudge(ValueError):
    def __init__(self, run_judge: str, judge: str) -> None:
        super().__init__(
            f"the run was judged by {run_judge} but the judge is now {judge}; "
            f"set EVAL_JUDGE_MODEL={run_judge} so the scores compare"
        )


class ChangedQuestionSet(ValueError):
    def __init__(self, run: RunSetup, current: QuestionSet) -> None:
        super().__init__(
            f"the run used {run.repo}@{run.ref} (questions v{run.dataset_version}), "
            f"but the question set is now {current.repo}@{current.ref} (v{current.version})"
        )


class Spread(BaseModel):
    model_config = ConfigDict(frozen=True)

    mean: float
    low: float
    high: float

    @classmethod
    def of(cls, values: Sequence[float]) -> Spread:
        return cls(mean=fmean(values), low=min(values), high=max(values))


class RegradeSetup(BaseModel):
    model_config = ConfigDict(frozen=True)

    started_at: AwareDatetime
    git_commit: str
    source: str
    reps: int
    judge_model: str


class GradedPass(BaseModel):
    model_config = ConfigDict(frozen=True)

    checks: dict[str, tuple[CheckResult, ...]]


class Regrade(BaseModel):
    model_config = ConfigDict(frozen=True)

    setup: RegradeSetup
    source_setup: RunSetup
    questions: tuple[QuestionScore, ...]
    passes: tuple[GradedPass, ...]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def metrics(self) -> tuple[AgentMetrics, ...]:
        return tuple(agent_metrics(self.scores_in(graded)) for graded in self.passes)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def summary(self) -> dict[str, Spread]:
        metrics = self.metrics
        if not metrics:
            return {}

        return {
            "fact_score": Spread.of([m.fact_score for m in metrics]),
            "all_facts_stated": Spread.of([m.all_facts_stated for m in metrics]),
            "faithfulness_passed": Spread.of([m.faithfulness.passed for m in metrics]),
            "inconclusive": Spread.of([m.inconclusive for m in metrics]),
        }

    @field_serializer("questions")
    def without_source_grades(self, questions: tuple[QuestionScore, ...]) -> list[dict[str, Any]]:
        # The source run's own verdicts would read as if they came from a pass.
        return [
            scored.model_dump(mode="json", exclude={"checks", "fact_score"}) for scored in questions
        ]

    def scores_in(self, graded: GradedPass) -> list[QuestionScore]:
        return [
            scored.model_copy(update={"checks": graded.checks[scored.id]})
            for scored in self.questions
        ]


@dataclass(frozen=True)
class RegradeRequest:
    source: Path
    reps: int
    judge_model: str


@dataclass(frozen=True)
class RegradePlan:
    setup: RegradeSetup
    source: AgentRun
    questions: Mapping[str, Question]
    repo: Path
    path: Path


def main(run: str, reps: str, config: AgentRunConfig = DEFAULT_CONFIG) -> int:
    """Re-judges the saved run at `run` `reps` times; returns the process exit code."""
    if not run:
        return stop(COMMAND, f"set {RUN_ENV} to an eval-agent results file")
    if not is_positive_number(reps):
        return stop(COMMAND, f"{REPS_ENV} must be a whole number above 0, not {reps!r}")

    try:
        eval_settings = EvalSettings()
        judge = build_judge(eval_settings)
    except (ValidationError, SettingsError) as error:
        return stop(COMMAND, f"bad setting: {describe_settings_error(error)}")
    except (ValueError, ImportError) as error:
        return stop(COMMAND, f"could not set up the judge {eval_settings.judge_model} ({error})")

    request = RegradeRequest(Path(run), int(reps), eval_settings.judge_model)
    try:
        plan = prepare(config, request)
        result = regrade_run(plan, judge)
    except (
        OSError,
        ValidationError,
        InvalidDataset,
        yaml.YAMLError,
        NotAnAgentRun,
        ChangedQuestionSet,
        ChangedJudge,
        UnknownQuestions,
        SampleRepoError,
        RepoCommitError,
        EvidenceMismatch,
    ) as error:
        return stop(COMMAND, error)
    except httpx.TransportError as error:
        reason = f"connection to Ollama at {eval_settings.ollama_base_url} failed ({error})"
        return stop(COMMAND, reason + saved_passes_note(plan.path))
    except ollama.ResponseError as error:
        return stop(
            COMMAND, f"Ollama could not run a model ({error})" + saved_passes_note(plan.path)
        )

    print(format_summary(result, plan.path))
    return 0


def is_positive_number(text: str) -> bool:
    return text.isascii() and text.isdigit() and int(text) > 0


def prepare(config: AgentRunConfig, request: RegradeRequest) -> RegradePlan:
    """Loads the run and checks it against the question set, so a mismatch costs no model call."""
    started_at = datetime.now(UTC)
    source = load_run(request.source)
    question_set = load_question_set(config.questions_path)
    if not is_same_question_set(source.setup, question_set):
        raise ChangedQuestionSet(source.setup, question_set)
    # Questions can be renamed or removed without the set's version changing.
    questions = select_questions(question_set, [scored.id for scored in source.questions])
    if source.setup.judge_model != request.judge_model:
        raise ChangedJudge(source.setup.judge_model, request.judge_model)
    clone = fetch_sample_repo(sample_repo_for(question_set), config.cache_dir)

    setup = RegradeSetup(
        started_at=started_at,
        git_commit=git_commit(),
        source=str(request.source),
        reps=request.reps,
        judge_model=request.judge_model,
    )
    path = config.results_dir / f"regrade-{started_at:{TIMESTAMP_FORMAT}}.json"

    return RegradePlan(
        setup=setup,
        source=source,
        questions={question.id: question for question in questions},
        repo=clone,
        path=path,
    )


def load_run(path: Path) -> AgentRun:
    try:
        return AgentRun.model_validate_json(path.read_text(encoding="utf-8"))
    except ValidationError as error:
        raise NotAnAgentRun(path) from error


def is_same_question_set(run: RunSetup, current: QuestionSet) -> bool:
    return (run.dataset_version, run.repo, run.ref) == (current.version, current.repo, current.ref)


def regrade_run(plan: RegradePlan, judge: BaseChatModel) -> Regrade:
    """Rewrites the results file after each pass, so a run that dies keeps its whole passes."""
    regrade = Regrade(
        setup=plan.setup,
        source_setup=plan.source.setup,
        questions=with_evidence(plan.source, plan.repo),
        passes=(),
    )

    for number in range(1, plan.setup.reps + 1):
        graded = grade_pass(regrade.questions, plan.questions, judge)
        regrade = regrade.model_copy(update={"passes": (*regrade.passes, graded)})
        progress = describe(agent_metrics(regrade.scores_in(graded)))
        print(f"[pass {number}/{plan.setup.reps}] {progress}", file=sys.stderr, flush=True)
        write_record(regrade, plan.path)

    return regrade


def with_evidence(source: AgentRun, repo: Path) -> tuple[QuestionScore, ...]:
    """The run's questions with evidence, replaying tool calls where the run saved none.

    Empty answers are never judged, so their evidence is neither replayed nor checked.
    """
    toolbox = Toolbox.over(DirectSearch(open_scope(repo, source.setup.agent.search_skip)))
    questions = tuple(
        replayed(scored, toolbox) if needs_replay(scored) else scored for scored in source.questions
    )

    mismatches = [
        (scored.id, scored.evidence_chars, len(scored.evidence))
        for scored in questions
        if not scored.is_empty and len(scored.evidence) != scored.evidence_chars
    ]
    if mismatches:
        raise EvidenceMismatch(mismatches)

    return questions


def needs_replay(scored: QuestionScore) -> bool:
    return not scored.is_empty and not scored.evidence and scored.evidence_chars > 0


def replayed(scored: QuestionScore, toolbox: Toolbox) -> QuestionScore:
    records = tuple(
        toolbox.execute(Call(call.name, call.args))
        for call in scored.tool_calls
        if call.outcome == Outcome.RAN.value
    )

    return scored.model_copy(update={"evidence": evidence(records)})


def grade_pass(
    scores: Sequence[QuestionScore], questions: Mapping[str, Question], judge: BaseChatModel
) -> GradedPass:
    return GradedPass(
        checks={scored.id: judged_checks(judge, questions[scored.id], scored) for scored in scores}
    )


def describe(metrics: AgentMetrics) -> str:
    return (
        f"all facts stated {metrics.all_facts_stated}, fact score {metrics.fact_score:.3f}, "
        f"faithfulness {metrics.faithfulness.passed} pass"
    )


def saved_passes_note(path: Path) -> str:
    return f"; finished passes are in {path}" if path.exists() else ""


def format_summary(regrade: Regrade, path: Path) -> str:
    source = agent_metrics(regrade.questions)
    summary = regrade.summary

    return format_rows(
        [
            ("questions", str(len(regrade.questions))),
            ("passes", str(len(regrade.passes))),
            ("recall@5", f"{source.recall_at_5:.3f}"),
            ("MRR", f"{source.mrr:.3f}"),
            ("fact score", format_spread(summary["fact_score"], ".3f")),
            ("all facts stated", format_spread(summary["all_facts_stated"], ".1f")),
            ("faithfulness passed", format_spread(summary["faithfulness_passed"], ".1f")),
            ("inconclusive", format_spread(summary["inconclusive"], ".1f")),
            ("results", str(path)),
        ]
    )


def format_spread(spread: Spread, spec: str) -> str:
    return f"{spread.mean:{spec}} ({spread.low:{spec}}–{spread.high:{spec}})"


if __name__ == "__main__":
    sys.exit(main(os.environ.get(RUN_ENV, ""), os.environ.get(REPS_ENV) or DEFAULT_REPS))
