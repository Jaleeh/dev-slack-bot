import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from evals.pii_set import PiiSet
from evals.question_set import QuestionSet
from evals.redactor import AnswerKeyRedactor, NoRedactor
from evals.retriever import AnswerKeyRetriever
from evals.run_record import RepoCommitError
from evals.runner import (
    STAND_INS,
    Contenders,
    Metrics,
    MissingFiles,
    RunConfig,
    evaluate,
    main,
    save,
)
from evals.sample_repo import SampleRepo, SampleRepoError, fetch_sample_repo

JANE_ROE = {
    "id": "jane-order",
    "kind": "question",
    "text": "Ask Jane Roe about order 100042.",
    "planted": [{"type": "PERSON", "value": "Jane Roe"}],
    "lookalikes": ["100042"],
}


class EmptyRetriever:
    name = "empty"

    def __init__(self, question_set: QuestionSet) -> None:
        pass

    def retrieve(self, question: str) -> list[str]:
        return []


def no_redactor(pii_set: PiiSet) -> NoRedactor:
    return NoRedactor()


def a_config(
    tmp_path: Path,
    origin_repo: Path,
    files: tuple[str, ...] = ("src/a.py",),
    pii_snippets: tuple[dict[str, Any], ...] = (JANE_ROE,),
) -> RunConfig:
    questions_path = tmp_path / "questions.yaml"
    question = {
        "id": "q1",
        "type": "how_it_works",
        "question": "How does a thing work?",
        "key_facts": ["It works one way.", "It works another way."],
        "files": list(files),
    }
    question_set = {"version": 1, "repo": "tiny", "ref": "v1", "questions": [question]}
    questions_path.write_text(yaml.safe_dump(question_set))

    pii_path = tmp_path / "pii.yaml"
    pii_path.write_text(yaml.safe_dump({"version": 1, "snippets": list(pii_snippets)}))

    return RunConfig(
        questions_path=questions_path,
        pii_path=pii_path,
        cache_dir=tmp_path / "cache",
        results_dir=tmp_path / "results",
        repo_urls={"tiny": origin_repo.as_uri()},
    )


def test_answer_key_scores_full_marks(origin_repo: Path, tmp_path: Path) -> None:
    run = evaluate(a_config(tmp_path, origin_repo), STAND_INS)

    assert run.metrics == Metrics(recall_at_5=1.0, recall_at_10=1.0, mrr=1.0)
    assert run.retriever == "answer-key"


def test_a_retriever_that_finds_nothing_scores_zero(origin_repo: Path, tmp_path: Path) -> None:
    run = evaluate(
        a_config(tmp_path, origin_repo),
        Contenders(build_retriever=EmptyRetriever, build_redactor=no_redactor),
    )

    assert run.metrics == Metrics(recall_at_5=0.0, recall_at_10=0.0, mrr=0.0)
    assert run.questions[0].ranked == ()


def test_no_redactor_catches_nothing(origin_repo: Path, tmp_path: Path) -> None:
    run = evaluate(a_config(tmp_path, origin_repo), STAND_INS)

    assert run.pii.redactor == "none (stand-in)"
    assert run.pii.metrics.catch_rate == 0.0
    assert run.pii.metrics.wrong_flag_rate == 0.0


def test_answer_key_redactor_catches_everything(origin_repo: Path, tmp_path: Path) -> None:
    contenders = Contenders(build_retriever=AnswerKeyRetriever, build_redactor=AnswerKeyRedactor)

    run = evaluate(a_config(tmp_path, origin_repo), contenders)

    assert run.pii.metrics.catch_rate == 1.0
    assert run.pii.snippets[0].missed == ()


def test_run_records_its_setup(origin_repo: Path, tmp_path: Path) -> None:
    run = evaluate(a_config(tmp_path, origin_repo), STAND_INS)

    assert (run.repo, run.ref, run.dataset_version) == ("tiny", "v1", 1)
    assert run.pii.dataset_version == 1
    assert run.started_at.tzinfo is not None
    assert run.git_commit
    assert run.questions[0].tokens is None
    assert run.questions[0].seconds >= 0


def test_stops_when_listed_files_are_missing(origin_repo: Path, tmp_path: Path) -> None:
    config = a_config(tmp_path, origin_repo, ("src/a.py", "src/lost.py", "src/gone.py"))

    with pytest.raises(MissingFiles) as raised:
        evaluate(config, STAND_INS)

    assert raised.value.paths == ("src/gone.py", "src/lost.py")


def test_stops_for_an_unknown_repo(origin_repo: Path, tmp_path: Path) -> None:
    config = a_config(tmp_path, origin_repo).model_copy(update={"repo_urls": {}})

    with pytest.raises(SampleRepoError, match="tiny"):
        evaluate(config, STAND_INS)


def test_save_writes_the_results_file(origin_repo: Path, tmp_path: Path) -> None:
    config = a_config(tmp_path, origin_repo)

    path = save(evaluate(config, STAND_INS), config.results_dir)

    data = json.loads(path.read_text())
    assert path.parent == config.results_dir
    assert path.name.endswith("Z.json")
    assert data["metrics"]["mrr"] == 1.0
    assert data["questions"][0]["id"] == "q1"
    assert data["pii"]["metrics"]["catch_rate"] == 0.0
    assert data["pii"]["snippets"][0]["id"] == "jane-order"


def test_main_prints_the_summary(
    origin_repo: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = a_config(tmp_path, origin_repo)

    exit_code = main(config)

    output = capsys.readouterr().out
    saved = next(config.results_dir.iterdir())
    assert exit_code == 0
    assert "answer-key" in output
    assert "1.000" in output
    assert "none (stand-in)" in output
    assert "catch rate" in output
    assert str(saved) in output


def test_main_prints_n_a_without_lookalikes(
    origin_repo: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = a_config(tmp_path, origin_repo, pii_snippets=({**JANE_ROE, "lookalikes": []},))

    exit_code = main(config)

    assert exit_code == 0
    assert "n/a" in capsys.readouterr().out


def test_main_reports_a_broken_question_set(
    origin_repo: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = a_config(tmp_path, origin_repo, ())

    exit_code = main(config)

    errors = capsys.readouterr().err
    assert exit_code == 1
    assert "q1" in errors
    assert "Traceback" not in errors


def test_main_reports_a_broken_pii_set(
    origin_repo: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    broken = {**JANE_ROE, "text": "Ask someone about order 100042."}
    config = a_config(tmp_path, origin_repo, pii_snippets=(broken,))

    exit_code = main(config)

    errors = capsys.readouterr().err
    assert exit_code == 1
    assert "jane-order" in errors
    assert "Traceback" not in errors


def outside_a_git_checkout(
    config: RunConfig, origin_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pre-fills the clone cache, then hides this repo's history from git."""
    fetch_sample_repo(SampleRepo("tiny", origin_repo.as_uri(), "v1"), config.cache_dir)
    monkeypatch.setenv("GIT_DIR", str(origin_repo / "no-such-git-dir"))


def never_called(question_set: QuestionSet) -> EmptyRetriever:
    raise AssertionError("retriever was built before the commit was read")


def test_stops_before_scoring_when_the_commit_cannot_be_read(
    origin_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = a_config(tmp_path, origin_repo)
    outside_a_git_checkout(config, origin_repo, monkeypatch)

    with pytest.raises(RepoCommitError):
        evaluate(config, Contenders(build_retriever=never_called, build_redactor=no_redactor))


def test_main_reports_an_unreadable_commit(
    origin_repo: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = a_config(tmp_path, origin_repo)
    outside_a_git_checkout(config, origin_repo, monkeypatch)

    exit_code = main(config)

    errors = capsys.readouterr().err
    assert exit_code == 1
    assert "commit" in errors
    assert "Traceback" not in errors
