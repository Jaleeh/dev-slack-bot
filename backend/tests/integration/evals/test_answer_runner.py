import json
from pathlib import Path

import httpx
import pytest
import yaml
from langchain_core.language_models import BaseChatModel

from evals import answer_runner
from evals.answer_runner import AnswerRunConfig, Counts, evaluate_answers, main, save
from tests.answer_datasets import a_question, a_question_set, an_answer_set, an_entry
from tests.fake_judge import YES, FakeJudge, FunctionJudge
from tests.support import UNREACHABLE_URL

JUDGE_MODEL = "fake:judge"


def a_config(tmp_path: Path, *question_ids: str) -> AnswerRunConfig:
    questions = a_question_set(a_question("q1", 3), a_question("q2", 2))
    answers = an_answer_set(*(an_entry(question_id=id_) for id_ in question_ids or ("q1", "q2")))
    questions_path = tmp_path / "questions.yaml"
    answers_path = tmp_path / "wrong_answers.yaml"
    questions_path.write_text(yaml.safe_dump(questions))
    answers_path.write_text(yaml.safe_dump(answers))

    return AnswerRunConfig(
        questions_path=questions_path,
        answers_path=answers_path,
        results_dir=tmp_path / "results",
    )


def use_judge(monkeypatch: pytest.MonkeyPatch, model: str, url: str) -> None:
    monkeypatch.setenv("CHAT_MODEL", model)
    monkeypatch.setenv("EVAL_JUDGE_MODEL", "")
    monkeypatch.setenv("OLLAMA_BASE_URL", url)


def test_a_judge_that_always_says_yes_is_counted(tmp_path: Path) -> None:
    run = evaluate_answers(a_config(tmp_path), FakeJudge(responses=[YES]), JUDGE_MODEL)

    # "Yes" passes every check: both correct answers are right, every wrong answer is missed.
    assert run.counts == Counts(right=2, wrong=8, inconclusive=0, ungraded_checks=0)


def test_results_file_records_the_judge_and_counts(tmp_path: Path) -> None:
    config = a_config(tmp_path)
    run = evaluate_answers(config, FakeJudge(responses=[YES]), JUDGE_MODEL)

    path = save(run, config.results_dir)

    saved = json.loads(path.read_text())
    assert path.name.startswith("answers-")
    assert saved["started_at"]
    assert saved["git_commit"]
    assert saved["dataset_version"] == 1
    assert saved["judge_model"] == JUDGE_MODEL
    assert saved["judge_temperature"] == 0
    assert saved["counts"] == {"right": 2, "wrong": 8, "inconclusive": 0, "ungraded_checks": 0}
    assert len(saved["answers"]) == 10
    assert saved["answers"][1]["checks"][1] == {"check": "fact-2", "outcome": "pass"}


def test_unreadable_replies_show_as_inconclusive(tmp_path: Path) -> None:
    run = evaluate_answers(a_config(tmp_path), FakeJudge(responses=["sure!"]), JUDGE_MODEL)

    # q1 has 4 checks per answer and q2 has 3, over 5 answers each.
    assert run.counts == Counts(right=0, wrong=0, inconclusive=10, ungraded_checks=35)


def test_main_stops_cleanly_when_ollama_is_down(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    use_judge(monkeypatch, "ollama:ornith:9b", UNREACHABLE_URL)
    config = a_config(tmp_path)

    assert main(config) == 1

    stderr = capsys.readouterr().err
    assert stderr.startswith("eval-answers stopped:")
    assert UNREACHABLE_URL in stderr
    assert not config.results_dir.exists()


def test_main_stops_cleanly_on_an_unknown_question(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    use_judge(monkeypatch, "ollama:ornith:9b", UNREACHABLE_URL)

    assert main(a_config(tmp_path, "q1", "no-such-question")) == 1

    assert "no-such-question" in capsys.readouterr().err


def test_main_stops_cleanly_when_the_model_is_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    ollama_url: str,
) -> None:
    use_judge(monkeypatch, "ollama:no-such-model:1b", ollama_url)

    assert main(a_config(tmp_path)) == 1

    assert "ollama:no-such-model:1b" in capsys.readouterr().err


def test_main_stops_cleanly_on_an_unknown_model_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    use_judge(monkeypatch, "olama:ornith:9b", UNREACHABLE_URL)

    assert main(a_config(tmp_path)) == 1

    stderr = capsys.readouterr().err
    assert stderr.startswith("eval-answers stopped:")
    assert "olama:ornith:9b" in stderr


def dropped_connection(prompt: str) -> object:
    raise httpx.ReadError("connection closed mid-reply")


def test_main_stops_cleanly_when_ollama_drops_mid_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def judge_that_drops(_: object) -> BaseChatModel:
        return FunctionJudge(reply=dropped_connection)

    use_judge(monkeypatch, "ollama:ornith:9b", UNREACHABLE_URL)
    monkeypatch.setattr(answer_runner, "build_judge", judge_that_drops)
    config = a_config(tmp_path)

    assert main(config) == 1

    assert UNREACHABLE_URL in capsys.readouterr().err
    assert not config.results_dir.exists()
