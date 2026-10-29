from datetime import UTC, datetime
from pathlib import Path

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage

from app.agent.graph import Agent
from app.config.agent import AgentSettings
from app.retrieval.direct.scope import open_scope
from app.retrieval.direct.search import DirectSearch
from evals.agent_runner import AgentRunPlan, Harness, RunSetup
from evals.question_set import Question
from tests.answer_datasets import a_question
from tests.scripted_model import ROOMY, scripted

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
