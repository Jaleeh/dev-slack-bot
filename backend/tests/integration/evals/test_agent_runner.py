import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
import yaml
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage

from app.agent.graph import Agent
from app.config.agent import AgentSettings
from app.retrieval.direct.scope import open_scope
from app.retrieval.direct.search import DirectSearch
from evals.agent_runner import (
    AgentRunConfig,
    AgentRunPlan,
    Harness,
    RunSetup,
    evaluate_agent,
    kept_note,
    main,
)
from evals.question_set import Question
from tests.answer_datasets import a_question, a_question_set
from tests.fake_judge import YES, FakeJudge, FunctionJudge
from tests.scripted_model import ROOMY, calls, scripted

BENEFITS = "src/oscar/apps/offer/benefits.py"
QUESTIONS = (a_question("q1", 2), a_question("q2", 2))


def a_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    for name in (BENEFITS, "src/other.py"):
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_text("class Benefit:\n    pass\n")

    return repo


def a_plan(tmp_path: Path, repo: Path) -> AgentRunPlan:
    setup = RunSetup(
        started_at=datetime.now(UTC),
        git_commit="abc123",
        dataset_version=1,
        repo="django-oscar",
        ref="4.2.1",
        ids=(),
        agent=AgentSettings(_env_file=None),
        judge_model="fake:judge",
    )
    questions = tuple(Question.model_validate(question) for question in QUESTIONS)

    return AgentRunPlan(setup=setup, questions=questions, repo=repo, path=tmp_path / "agent.json")


def a_harness(
    repo: Path, search_replies: list[AIMessage | str], rewrites: list[str], judge: BaseChatModel
) -> Harness:
    agent = Agent(
        scripted(*search_replies),
        scripted(*rewrites),
        DirectSearch(open_scope(repo)),
        ROOMY,
    )

    return Harness(agent=agent, judge=judge)


def test_results_file_holds_setup_metrics_and_each_question(tmp_path: Path) -> None:
    # q1 reads the right file and answers; q2 only greps, then gives no answer.
    replies: list[AIMessage | str] = [
        calls(("read_file", {"path": BENEFITS})),
        "draft",
        calls(("grep", {"pattern": "x"})),
        "",
    ]
    repo = a_repo(tmp_path)
    harness = a_harness(repo, replies, ["answer"], FakeJudge(responses=[YES]))
    plan = a_plan(tmp_path, repo)

    evaluate_agent(plan, harness)

    saved = json.loads(plan.path.read_text())
    assert saved["setup"]["ids"] == []
    assert saved["metrics"]["recall_at_5"] == 0.5
    assert saved["metrics"]["fact_score"] == 0.5
    assert saved["metrics"]["empty"] == 1
    assert saved["metrics"]["faithfulness"]["passed"] == 1
    assert saved["questions"][0]["files"] == [BENEFITS]
    assert saved["questions"][1]["checks"] == []
    assert saved["questions"][1]["is_empty"]


def test_finished_questions_are_kept_when_the_run_dies(tmp_path: Path) -> None:
    def down_on_the_second_answer(prompt: object) -> dict[str, str]:
        if "answer two" in str(prompt):
            raise httpx.ConnectError("down")
        return {"answer": "yes"}

    replies: list[AIMessage | str] = [
        calls(("read_file", {"path": BENEFITS})),
        "one",
        calls(("grep", {"pattern": "x"})),
        "2",
    ]
    judge = FunctionJudge(reply=down_on_the_second_answer)
    repo = a_repo(tmp_path)
    harness = a_harness(repo, replies, ["answer one", "answer two"], judge)
    plan = a_plan(tmp_path, repo)

    with pytest.raises(httpx.ConnectError):
        evaluate_agent(plan, harness)

    saved = json.loads(plan.path.read_text())
    assert [question["id"] for question in saved["questions"]] == ["q1"]


def test_stop_message_names_the_saved_file_and_how_to_rerun(tmp_path: Path) -> None:
    path = tmp_path / "agent.json"
    path.write_text("{}")

    note = kept_note(path)

    assert str(path) in note
    assert "IDS=" in note


@pytest.fixture
def config(tmp_path: Path, sample_cache: Path) -> AgentRunConfig:
    questions_path = tmp_path / "questions.yaml"
    questions_path.write_text(yaml.safe_dump(a_question_set(*QUESTIONS)))

    return AgentRunConfig(
        questions_path=questions_path,
        cache_dir=sample_cache,
        results_dir=tmp_path / "results",
    )


@pytest.mark.usefixtures("offline_model")
def test_main_stops_on_an_unknown_id_before_any_model_call(
    config: AgentRunConfig, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["no-such-id"], config) == 1

    stderr = capsys.readouterr().err
    assert stderr.startswith("eval-agent stopped:")
    assert "no-such-id" in stderr
    assert "connection to Ollama" not in stderr
    assert not config.results_dir.exists()


@pytest.mark.usefixtures("offline_model")
def test_main_stops_cleanly_when_ollama_is_unreachable(
    config: AgentRunConfig, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["q1"], config) == 1

    assert "connection to Ollama" in capsys.readouterr().err
