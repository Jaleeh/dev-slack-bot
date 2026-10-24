"""Scores a retriever and a redactor against the eval sets and records the run."""

import sys
import time
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from statistics import fmean

import yaml
from pydantic import AwareDatetime, BaseModel, ConfigDict

from evals.dataset_file import InvalidDataset
from evals.pii_metrics import PiiMetrics, SnippetResult, pii_metrics, score_snippet
from evals.pii_set import PII_PATH, PiiSet, load_pii_set
from evals.question_set import (
    QUESTIONS_PATH,
    Question,
    QuestionSet,
    load_question_set,
)
from evals.redactor import NoRedactor, Redactor
from evals.retrieval_metrics import recall_at_k, reciprocal_rank
from evals.retriever import AnswerKeyRetriever, Retriever
from evals.run_record import (
    EVALS_DIR,
    TIMESTAMP_FORMAT,
    RepoCommitError,
    format_rows,
    git_commit,
    stop,
    write_record,
)
from evals.sample_repo import REPO_URLS, SampleRepo, SampleRepoError, fetch_sample_repo


class RunConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    questions_path: Path = QUESTIONS_PATH
    pii_path: Path = PII_PATH
    cache_dir: Path = EVALS_DIR / ".cache"
    results_dir: Path = EVALS_DIR / "results"
    repo_urls: Mapping[str, str] = REPO_URLS


DEFAULT_CONFIG = RunConfig()


class Contenders(BaseModel):
    model_config = ConfigDict(frozen=True)

    build_retriever: Callable[[QuestionSet], Retriever]
    build_redactor: Callable[[PiiSet], Redactor]


STAND_INS = Contenders(build_retriever=AnswerKeyRetriever, build_redactor=lambda _: NoRedactor())


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


class PiiResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    dataset_version: int
    redactor: str
    metrics: PiiMetrics
    snippets: tuple[SnippetResult, ...]


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
    pii: PiiResult


class MissingFiles(Exception):
    def __init__(self, paths: tuple[str, ...]) -> None:
        super().__init__(
            "files in the question set are missing from the sample repo: " + ", ".join(paths)
        )
        self.paths = paths


def main(config: RunConfig = DEFAULT_CONFIG) -> int:
    """Scores the stand-ins; returns the process exit code."""
    try:
        run = evaluate(config, STAND_INS)
    except (
        InvalidDataset,
        yaml.YAMLError,
        SampleRepoError,
        MissingFiles,
        RepoCommitError,
    ) as error:
        return stop("eval", error)

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
        ("redactor", run.pii.redactor),
        ("catch rate", _format_rate(run.pii.metrics.catch_rate)),
        ("wrong flags", _format_rate(run.pii.metrics.wrong_flag_rate)),
        ("results", str(path)),
    ]

    return format_rows(rows)


def evaluate(config: RunConfig, contenders: Contenders) -> RunResult:
    """Raises before scoring on a bad dataset, failed fetch, missing file or unknown commit."""
    started_at = datetime.now(UTC)
    commit = git_commit()
    question_set = load_question_set(config.questions_path)
    pii_set = load_pii_set(config.pii_path)

    clone = fetch_sample_repo(_sample_repo(question_set, config.repo_urls), config.cache_dir)
    missing = _missing_files(question_set, clone)
    if missing:
        raise MissingFiles(missing)

    retriever = contenders.build_retriever(question_set)
    results = tuple(_run_question(retriever, question) for question in question_set.questions)
    pii = _run_pii_set(contenders.build_redactor(pii_set), pii_set)

    return RunResult(
        started_at=started_at,
        git_commit=commit,
        dataset_version=question_set.version,
        repo=question_set.repo,
        ref=question_set.ref,
        retriever=retriever.name,
        metrics=_mean_metrics(results),
        questions=results,
        pii=pii,
    )


def save(run: RunResult, results_dir: Path) -> Path:
    return write_record(run, results_dir / f"{run.started_at:{TIMESTAMP_FORMAT}}.json")


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


def _run_pii_set(redactor: Redactor, pii_set: PiiSet) -> PiiResult:
    snippets = pii_set.snippets
    results = tuple(score_snippet(snippet, redactor.redact(snippet.text)) for snippet in snippets)

    return PiiResult(
        dataset_version=pii_set.version,
        redactor=redactor.name,
        metrics=pii_metrics(snippets, results),
        snippets=results,
    )


def _format_rate(rate: float | None) -> str:
    return "n/a" if rate is None else f"{rate:.3f}"


if __name__ == "__main__":
    sys.exit(main())
