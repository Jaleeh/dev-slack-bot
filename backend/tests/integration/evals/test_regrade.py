import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from langchain_core.messages import AIMessage

from evals.agent_runner import AgentRunConfig, evaluate_agent
from evals.question_set import Question
from evals.regrade import (
    EvidenceMismatch,
    RegradePlan,
    RegradeSetup,
    Spread,
    load_run,
    main,
    regrade_run,
)
from tests.fake_judge import YES, FakeJudge, FunctionJudge
from tests.integration.evals.agent_runs import BENEFITS, QUESTIONS, a_harness, a_plan, a_repo
from tests.scripted_model import calls

# q1 has two key facts plus faithfulness; q2 gives no answer, so is never judged.
CHECKS_PER_PASS = 3
YES_REPLY = {"answer": "yes"}


def a_saved_run(tmp_path: Path) -> Path:
    """A real eval-agent results file: q1 reads the right file and answers, q2 answers nothing."""
    replies: list[AIMessage | str] = [
        calls(("read_file", {"path": BENEFITS})),
        "draft",
        calls(("grep", {"pattern": "Benefit"})),
        "",
    ]
    repo = a_repo(tmp_path)
    plan = a_plan(tmp_path, repo)

    evaluate_agent(plan, a_harness(repo, replies, ["answer"], FakeJudge(responses=[YES])))

    return plan.path


def edit_run(path: Path, change: Callable[[dict[str, Any]], None]) -> None:
    saved = json.loads(path.read_text())
    change(saved)
    path.write_text(json.dumps(saved))


def drop_evidence(saved: dict[str, Any]) -> None:
    """Makes the run look like one saved before evidence was kept."""
    for question in saved["questions"]:
        del question["evidence"]


def a_regrade_plan(tmp_path: Path, source: Path, reps: int) -> RegradePlan:
    setup = RegradeSetup(
        started_at=datetime.now(UTC),
        git_commit="abc123",
        source=str(source),
        reps=reps,
        judge_model="fake:judge",
    )
    questions = {question["id"]: Question.model_validate(question) for question in QUESTIONS}

    return RegradePlan(
        setup=setup,
        source=load_run(source),
        questions=questions,
        repo=tmp_path / "repo",
        path=tmp_path / "regrade.json",
    )


def test_old_run_is_replayed_and_judged_each_pass(tmp_path: Path) -> None:
    source = a_saved_run(tmp_path)
    edit_run(source, drop_evidence)
    prompts: list[str] = []

    def says_yes(prompt: object) -> dict[str, str]:
        prompts.append(str(prompt))
        return {"answer": "yes"}

    result = regrade_run(a_regrade_plan(tmp_path, source, 2), FunctionJudge(reply=says_yes))

    assert any("class Benefit:" in prompt for prompt in prompts)
    assert len(result.passes) == 2
    assert all(graded.checks["q2"] == () for graded in result.passes)
    assert len(json.loads((tmp_path / "regrade.json").read_text())["passes"]) == 2


def test_replay_that_differs_from_the_record_stops_naming_the_question(tmp_path: Path) -> None:
    source = a_saved_run(tmp_path)
    edit_run(source, drop_evidence)
    edit_run(source, lambda saved: saved["questions"][0].update(evidence_chars=1))
    prompts: list[object] = []

    def records(prompt: object) -> dict[str, str]:
        prompts.append(prompt)
        return {"answer": "yes"}

    with pytest.raises(EvidenceMismatch, match="q1"):
        regrade_run(a_regrade_plan(tmp_path, source, 1), FunctionJudge(reply=records))

    assert prompts == []
    assert not (tmp_path / "regrade.json").exists()


def test_spread_covers_every_pass(tmp_path: Path) -> None:
    source = a_saved_run(tmp_path)
    count: list[int] = []

    def yes_then_no(prompt: object) -> dict[str, str]:
        count.append(1)
        return {"answer": "yes" if len(count) <= CHECKS_PER_PASS else "no"}

    result = regrade_run(a_regrade_plan(tmp_path, source, 2), FunctionJudge(reply=yes_then_no))

    assert result.summary["all_facts_stated"] == Spread(mean=0.5, low=0, high=1)


def test_finished_passes_are_kept_when_the_judge_dies(tmp_path: Path) -> None:
    source = a_saved_run(tmp_path)
    count: list[int] = []

    def down_in_the_second_pass(prompt: object) -> dict[str, str]:
        count.append(1)
        if len(count) > CHECKS_PER_PASS:
            raise httpx.ConnectError("down")
        return {"answer": "yes"}

    with pytest.raises(httpx.ConnectError):
        regrade_run(
            a_regrade_plan(tmp_path, source, 2), FunctionJudge(reply=down_in_the_second_pass)
        )

    assert len(json.loads((tmp_path / "regrade.json").read_text())["passes"]) == 1


@pytest.mark.usefixtures("offline_model")
def test_main_stops_when_the_run_file_is_missing(
    tmp_path: Path, config: AgentRunConfig, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = tmp_path / "nope.json"

    assert main(str(missing), "5", config) == 1

    stderr = capsys.readouterr().err
    assert stderr.startswith("regrade stopped:")
    assert str(missing) in stderr


@pytest.mark.usefixtures("offline_model")
@pytest.mark.parametrize("reps", ["0", "abc", "²"])
def test_main_refuses_reps_that_are_not_a_positive_number(
    tmp_path: Path, config: AgentRunConfig, reps: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(str(tmp_path / "never-read.json"), reps, config) == 1

    assert "REPS" in capsys.readouterr().err


@pytest.mark.usefixtures("offline_model")
def test_main_stops_when_the_question_set_changed(
    tmp_path: Path, config: AgentRunConfig, capsys: pytest.CaptureFixture[str]
) -> None:
    source = a_saved_run(tmp_path)
    edit_run(source, lambda saved: saved["setup"].update(ref="9.9.9"))

    assert main(str(source), "5", config) == 1

    stderr = capsys.readouterr().err
    assert "9.9.9" in stderr
    assert "4.2.1" in stderr
    assert not config.results_dir.exists()


@pytest.mark.usefixtures("offline_model")
def test_main_stops_in_one_line_when_the_file_is_not_an_agent_run(
    tmp_path: Path, config: AgentRunConfig, capsys: pytest.CaptureFixture[str]
) -> None:
    not_a_run = tmp_path / "regrade.json"
    not_a_run.write_text('{"passes": []}')

    assert main(str(not_a_run), "5", config) == 1

    stderr = capsys.readouterr().err
    assert stderr.count("\n") == 1
    assert str(not_a_run) in stderr


@pytest.mark.usefixtures("offline_model")
def test_main_stops_naming_questions_no_longer_in_the_set(
    tmp_path: Path, config: AgentRunConfig, capsys: pytest.CaptureFixture[str]
) -> None:
    source = a_saved_run(tmp_path)
    edit_run(source, lambda saved: saved["questions"][0].update(id="renamed-away"))

    assert main(str(source), "5", config) == 1

    assert "renamed-away" in capsys.readouterr().err
    assert not config.results_dir.exists()


def test_unjudged_empty_answers_are_not_replayed(tmp_path: Path) -> None:
    source = a_saved_run(tmp_path)
    edit_run(source, drop_evidence)
    edit_run(source, lambda saved: saved["questions"][1].update(evidence_chars=1))

    result = regrade_run(
        a_regrade_plan(tmp_path, source, 1), FunctionJudge(reply=lambda _: YES_REPLY)
    )

    assert len(result.passes) == 1


def test_saved_questions_hold_no_grades_from_the_source_run(tmp_path: Path) -> None:
    source = a_saved_run(tmp_path)

    regrade_run(a_regrade_plan(tmp_path, source, 1), FunctionJudge(reply=lambda _: YES_REPLY))

    saved = json.loads((tmp_path / "regrade.json").read_text())
    assert all("checks" not in question for question in saved["questions"])
    assert all("fact_score" not in question for question in saved["questions"])


@pytest.mark.usefixtures("offline_model")
def test_main_stops_when_the_judge_differs_from_the_run(
    tmp_path: Path, config: AgentRunConfig, capsys: pytest.CaptureFixture[str]
) -> None:
    source = a_saved_run(tmp_path)

    assert main(str(source), "5", config) == 1

    stderr = capsys.readouterr().err
    assert "fake:judge" in stderr
    assert "ollama:ornith:9b" in stderr
    assert not config.results_dir.exists()
