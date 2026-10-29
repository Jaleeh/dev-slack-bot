from typing import Any

import pytest

from app.agent.graph import AgentResult, ToolCallRecord
from app.agent.guardrails import Outcome, StopReason
from evals.agent_scores import (
    Attempt,
    FaithfulnessCounts,
    QuestionScore,
    UnknownQuestions,
    agent_metrics,
    evidence,
    score,
    select_questions,
)
from evals.grader import CheckOutcome, CheckResult
from evals.question_set import Question, QuestionSet
from tests.answer_datasets import a_question, a_question_set


def a_result(**overrides: Any) -> AgentResult:
    return AgentResult(
        **{
            "answer": "An answer.",
            "draft": "A draft.",
            "stop": StopReason.ANSWERED,
            "tool_calls": (),
            "files": (),
            "model_calls": (),
            "tokens": 100,
            "seconds": 10.0,
            **overrides,
        }
    )


def a_record(name: str, output: str, outcome: Outcome) -> ToolCallRecord:
    return ToolCallRecord(name, {"pattern": "voucher"}, output, outcome)


def question_set() -> QuestionSet:
    return QuestionSet.model_validate(a_question_set(a_question("q1", 2), a_question("q2", 2)))


def graded(*outcomes: CheckOutcome) -> QuestionScore:
    """A score for an answer whose fact checks, then faithfulness, came out as given."""
    *facts, faithfulness = outcomes
    checks = (
        *(CheckResult(check=f"fact-{n}", outcome=o) for n, o in enumerate(facts, start=1)),
        CheckResult(check="faithfulness", outcome=faithfulness),
    )

    return score(a_question_model(), Attempt(result=a_result(), checks=checks, evidence=""))


def empty() -> QuestionScore:
    return score(a_question_model(), Attempt(result=a_result(draft=""), checks=(), evidence=""))


def a_question_model(**overrides: Any) -> Question:
    return Question.model_validate({**a_question("q1", 2), **overrides})


def test_no_ids_selects_every_question() -> None:
    selected = select_questions(question_set(), [])

    assert [question.id for question in selected] == ["q1", "q2"]


def test_selected_questions_keep_dataset_order() -> None:
    selected = select_questions(question_set(), ["q2", "q1"])

    assert [question.id for question in selected] == ["q1", "q2"]


def test_unknown_id_is_refused_naming_it() -> None:
    with pytest.raises(UnknownQuestions, match="nope") as caught:
        select_questions(question_set(), ["q1", "nope"])

    assert caught.value.ids == ("nope",)


def test_evidence_holds_only_output_from_calls_that_ran() -> None:
    records = (
        a_record("grep", "hit", Outcome.RAN),
        a_record("grep", "blocked", Outcome.REPEAT),
        a_record("read_file", "no such file", Outcome.FAILED),
    )

    text = evidence(records)

    assert "hit" in text
    assert "blocked" not in text
    assert "no such file" not in text


def test_score_ranks_against_the_question_files() -> None:
    question = a_question_model(files=["src/a.py"])
    attempt = Attempt(result=a_result(files=("src/b.py", "src/a.py")), checks=(), evidence="")

    scored = score(question, attempt)

    assert scored.recall_at_5 == 1.0
    assert scored.reciprocal_rank == 0.5


def test_empty_answer_scores_zero_and_stays_out_of_faithfulness() -> None:
    metrics = agent_metrics([graded("pass", "pass", "pass"), empty()])

    assert metrics.fact_score == 0.5
    assert metrics.empty == 1
    assert metrics.faithfulness == FaithfulnessCounts(passed=1, failed=0, unclear=0, ungraded=0)


def test_all_facts_stated_counts_only_answers_with_every_fact() -> None:
    metrics = agent_metrics([graded("pass", "pass", "pass"), graded("pass", "fail", "pass")])

    assert metrics.all_facts_stated == 1


def test_inconclusive_counts_answers_with_an_unclear_or_ungraded_check() -> None:
    metrics = agent_metrics(
        [
            graded("pass", "pass", "unclear"),
            graded("ungraded", "pass", "pass"),
            graded("pass", "pass", "pass"),
        ]
    )

    assert metrics.inconclusive == 2
