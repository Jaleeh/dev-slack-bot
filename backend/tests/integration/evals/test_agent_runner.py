import json
from pathlib import Path

import httpx
import pytest
from langchain_core.messages import AIMessage

from evals.agent_runner import AgentRunConfig, evaluate_agent, kept_note, main
from tests.fake_judge import YES, FakeJudge, FunctionJudge
from tests.integration.evals.agent_runs import BENEFITS, a_harness, a_plan, a_repo
from tests.scripted_model import calls


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
    assert saved["questions"][0]["evidence"].startswith(f"# read_file(path='{BENEFITS}')\n")
    assert saved["questions"][0]["evidence_chars"] == len(saved["questions"][0]["evidence"])
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
