"""Scores a retriever against the question set and records the run."""

import subprocess
import sys
import time
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from statistics import fmean

import yaml
from pydantic import AwareDatetime, BaseModel, ConfigDict

from evals.dataset_file import InvalidDataset
from evals.question_set import (
    QUESTIONS_PATH,
    Question,
    QuestionSet,
    load_question_set,
)
from evals.retrieval_metrics import recall_at_k, reciprocal_rank
from evals.retriever import AnswerKeyRetriever, Retriever
from evals.sample_repo import REPO_URLS, SampleRepo, SampleRepoError, fetch_sample_repo

EVALS_DIR = Path(__file__).parent


class RunConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    questions_path: Path = QUESTIONS_PATH
    cache_dir: Path = EVALS_DIR / ".cache"
    results_dir: Path = EVALS_DIR / "results"
    repo_urls: Mapping[str, str] = REPO_URLS


DEFAULT_CONFIG = RunConfig()


class QuestionResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    ranked: tuple[str, ...]
    recall_at_5: float
    recall_at_10: float
    reciprocal_rank: float
    seconds: float
    tokens: int | None


class Metrics(BaseModel):
    model_config = ConfigDict(frozen=True)

    recall_at_5: float
    recall_at_10: float
    mrr: float


class RunResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    started_at: AwareDatetime
    git_commit: str
    dataset_version: int
    repo: str
    ref: str
    retriever: str
    metrics: Metrics
    questions: tuple[QuestionResult, ...]


class RepoCommitError(RuntimeError):
    pass


class MissingFiles(Exception):
    def __init__(self, paths: tuple[str, ...]) -> None:
        super().__init__(
            "files in the question set are missing from the sample repo: " + ", ".join(paths)
        )
        self.paths = paths


def main(config: RunConfig = DEFAULT_CONFIG) -> int:
    """Scores the answer-key stand-in; returns the process exit code."""
    try:
        run = evaluate(config, AnswerKeyRetriever)
    except (
        InvalidDataset,
        yaml.YAMLError,
        SampleRepoError,
        MissingFiles,
        RepoCommitError,
    ) as error:
        print(f"eval stopped: {error}", file=sys.stderr)
        return 1

    path = save(run, config.results_dir)
    print(format_summary(run, path))

    return 0


def format_summary(run: RunResult, path: Path) -> str:
    rows = [
        ("retriever", run.retriever),
        ("questions", str(len(run.questions))),
        ("recall@5", f"{run.metrics.recall_at_5:.3f}"),
        ("recall@10", f"{run.metrics.recall_at_10:.3f}"),
        ("MRR", f"{run.metrics.mrr:.3f}"),
        ("results", str(path)),
    ]
    width = max(len(label) for label, _ in rows)

    return "\n".join(f"{label:<{width}}  {value}" for label, value in rows)


def evaluate(config: RunConfig, build_retriever: Callable[[QuestionSet], Retriever]) -> RunResult:
    """Raises before scoring on a bad question set, failed fetch, missing file or unknown commit."""
    started_at = datetime.now(UTC)
    git_commit = _git_commit()
    question_set = load_question_set(config.questions_path)

    clone = fetch_sample_repo(_sample_repo(question_set, config.repo_urls), config.cache_dir)
    missing = _missing_files(question_set, clone)
    if missing:
        raise MissingFiles(missing)

    retriever = build_retriever(question_set)
    results = tuple(_run_question(retriever, question) for question in question_set.questions)

    return RunResult(
        started_at=started_at,
        git_commit=git_commit,
        dataset_version=question_set.version,
        repo=question_set.repo,
        ref=question_set.ref,
        retriever=retriever.name,
        metrics=_mean_metrics(results),
        questions=results,
    )


def save(run: RunResult, results_dir: Path) -> Path:
    results_dir.mkdir(parents=True, exist_ok=True)
    path = results_dir / f"{run.started_at:%Y%m%dT%H%M%SZ}.json"

    path.write_text(run.model_dump_json(indent=2) + "\n", encoding="utf-8")

    return path


def _sample_repo(question_set: QuestionSet, repo_urls: Mapping[str, str]) -> SampleRepo:
    url = repo_urls.get(question_set.repo)
    if url is None:
        raise SampleRepoError(f"no URL known for repo {question_set.repo}")

    return SampleRepo(name=question_set.repo, url=url, ref=question_set.ref)


def _missing_files(question_set: QuestionSet, clone: Path) -> tuple[str, ...]:
    listed = {path for question in question_set.questions for path in question.files}

    return tuple(sorted(path for path in listed if not (clone / path).is_file()))


def _run_question(retriever: Retriever, question: Question) -> QuestionResult:
    start = time.perf_counter()
    ranked = retriever.retrieve(question.question)
    seconds = time.perf_counter() - start

    return _score(question, ranked, seconds)


def _score(question: Question, ranked: list[str], seconds: float) -> QuestionResult:
    relevant = set(question.files)

    return QuestionResult(
        id=question.id,
        ranked=tuple(ranked),
        recall_at_5=recall_at_k(ranked, relevant, 5),
        recall_at_10=recall_at_k(ranked, relevant, 10),
        reciprocal_rank=reciprocal_rank(ranked, relevant),
        seconds=seconds,
        tokens=None,
    )


def _mean_metrics(results: tuple[QuestionResult, ...]) -> Metrics:
    return Metrics(
        recall_at_5=fmean(result.recall_at_5 for result in results),
        recall_at_10=fmean(result.recall_at_10 for result in results),
        mrr=fmean(result.reciprocal_rank for result in results),
    )


def _git_commit() -> str:
    commit = _git("rev-parse", "HEAD")

    # A run from uncommitted code can't be reproduced from the commit alone.
    return f"{commit}-dirty" if _git("status", "--porcelain") else commit


def _git(*args: str) -> str:
    try:
        completed = subprocess.run(
            ["git", *args], cwd=EVALS_DIR, check=True, capture_output=True, text=True
        )
    except (FileNotFoundError, subprocess.CalledProcessError) as error:
        raise RepoCommitError(f"could not read this repo's commit: {error}") from error

    return completed.stdout.strip()


if __name__ == "__main__":
    sys.exit(main())
