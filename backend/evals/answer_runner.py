"""Grades the planted answers and records whether the grader got each one right."""

import sys
from collections import Counter
from datetime import UTC, datetime
from itertools import groupby
from pathlib import Path
from typing import Literal

import httpx
import ollama
import yaml
from langchain_core.language_models import BaseChatModel
from pydantic import AwareDatetime, BaseModel, ConfigDict, computed_field

from evals.answer_set import ANSWERS_PATH, AnswerEntry, load_answer_set
from evals.dataset_file import InvalidDataset
from evals.grader import (
    CheckResult,
    Outcome,
    fact_score,
    grade,
    outcome_for_correct,
    outcome_for_wrong,
)
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
from evals.settings import JUDGE_TEMPERATURE, EvalSettings, build_judge

ALL_PASS = "all pass"
COMMAND = "eval-answers"


class AnswerRunConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    questions_path: Path = QUESTIONS_PATH
    answers_path: Path = ANSWERS_PATH
    results_dir: Path = EVALS_DIR / "results"


DEFAULT_CONFIG = AnswerRunConfig()


class AnswerResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    question_id: str
    answer: Literal["correct"] | int
    expected: str
    outcome: Outcome
    checks: tuple[CheckResult, ...]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def fact_score(self) -> float:
        return fact_score(self.checks)


class Counts(BaseModel):
    model_config = ConfigDict(frozen=True)

    right: int
    wrong: int
    inconclusive: int
    ungraded_checks: int


class AnswerRun(BaseModel):
    model_config = ConfigDict(frozen=True)

    started_at: AwareDatetime
    git_commit: str
    dataset_version: int
    judge_model: str
    judge_temperature: int
    answers: tuple[AnswerResult, ...]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def counts(self) -> Counts:
        outcomes = Counter(answer.outcome for answer in self.answers)
        checks = (check for answer in self.answers for check in answer.checks)

        return Counts(
            right=outcomes["right"],
            wrong=outcomes["wrong"],
            inconclusive=outcomes["inconclusive"],
            ungraded_checks=sum(check.outcome == "ungraded" for check in checks),
        )


def main(config: AnswerRunConfig = DEFAULT_CONFIG) -> int:
    """Grades the planted answers with the configured judge; returns the process exit code."""
    settings = EvalSettings()
    try:
        judge = build_judge(settings)
    except (ValueError, ImportError) as error:
        return stop(COMMAND, f"could not set up the judge {settings.judge_model} ({error})")

    try:
        run = evaluate_answers(config, judge, settings.judge_model)
    except (InvalidDataset, yaml.YAMLError, RepoCommitError) as error:
        return stop(COMMAND, error)
    except httpx.TransportError as error:
        return stop(COMMAND, f"connection to Ollama at {settings.ollama_base_url} failed ({error})")
    except ollama.ResponseError as error:
        return stop(COMMAND, f"Ollama could not run {settings.judge_model} ({error})")

    path = save(run, config.results_dir)
    print(format_summary(run, path))

    return 0


def evaluate_answers(config: AnswerRunConfig, judge: BaseChatModel, judge_model: str) -> AnswerRun:
    """Loads both datasets before the first model call, so a bad dataset costs no grading."""
    started_at = datetime.now(UTC)
    commit = git_commit()
    question_set = load_question_set(config.questions_path)
    answer_set = load_answer_set(config.answers_path, question_set)
    questions = {question.id: question for question in question_set.questions}
    total = len(answer_set.answers)

    answers = tuple(
        result
        for number, entry in enumerate(answer_set.answers, start=1)
        for result in _logged(
            f"[{number}/{total}]", _grade_entry(judge, entry, questions[entry.question_id])
        )
    )

    return AnswerRun(
        started_at=started_at,
        git_commit=commit,
        dataset_version=answer_set.version,
        judge_model=judge_model,
        judge_temperature=JUDGE_TEMPERATURE,
        answers=answers,
    )


def save(run: AnswerRun, results_dir: Path) -> Path:
    return write_record(run, results_dir / f"answers-{run.started_at:{TIMESTAMP_FORMAT}}.json")


def format_summary(run: AnswerRun, path: Path) -> str:
    entries = [
        (question_id, " · ".join(_describe(result) for result in results))
        for question_id, results in groupby(run.answers, key=lambda result: result.question_id)
    ]
    counts = [
        (name.replace("_", " "), str(value)) for name, value in run.counts.model_dump().items()
    ]

    return format_rows(
        [*entries, ("", ""), ("judge", run.judge_model), *counts, ("results", str(path))]
    )


def _grade_entry(
    judge: BaseChatModel, entry: AnswerEntry, question: Question
) -> tuple[AnswerResult, ...]:
    correct = grade(judge, question, entry.correct, entry.code)
    wrong_grades = [grade(judge, question, wrong.answer, entry.code) for wrong in entry.wrong]
    numbered_wrongs = enumerate(zip(entry.wrong, wrong_grades, strict=True), start=1)

    return (
        AnswerResult(
            question_id=question.id,
            answer="correct",
            expected=ALL_PASS,
            outcome=outcome_for_correct(correct),
            checks=correct.checks,
        ),
        *(
            AnswerResult(
                question_id=question.id,
                answer=number,
                expected=wrong.fails,
                outcome=outcome_for_wrong(result, wrong),
                checks=result.checks,
            )
            for number, (wrong, result) in numbered_wrongs
        ),
    )


def _logged(position: str, results: tuple[AnswerResult, ...]) -> tuple[AnswerResult, ...]:
    """Prints one progress line for a graded entry and passes its results through."""
    described = " · ".join(_describe(result) for result in results)
    print(f"{position} {results[0].question_id}: {described}", file=sys.stderr, flush=True)

    return results


def _describe(result: AnswerResult) -> str:
    name = "correct" if result.answer == "correct" else f"wrong {result.answer}"

    return f"{name} {result.outcome}"


if __name__ == "__main__":
    sys.exit(main())
