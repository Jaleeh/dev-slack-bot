from langchain_core.exceptions import OutputParserException

from evals.answer_set import WrongAnswer
from evals.grader import RETRY_NUDGE, Grade, Verdict, grade, outcome_for_correct, outcome_for_wrong
from evals.question_set import Question
from tests.fake_judge import NO, UNCLEAR, YES, FakeJudge, FunctionJudge

UNREADABLE = "sure!"

QUESTION = Question.model_validate(
    {
        "id": "offer-repeat",
        "type": "how_it_works",
        "question": "Does the customer get one free item or one for every three they buy?",
        "key_facts": [
            "The customer gets one free item per basket.",
            "The cheapest qualifying item is the one that's free.",
        ],
        "files": ["src/oscar/apps/offer/benefits.py"],
    }
)


def grade_with(*replies: str) -> Grade:
    return grade(FakeJudge(responses=list(replies)), QUESTION, "An answer.", "# a.py\n")


def outcomes(result: Grade) -> dict[str, str]:
    return {check.check: check.outcome for check in result.checks}


def a_grade(**outcomes_by_check: str) -> Grade:
    checks = {"fact-1": "pass", "fact-2": "pass", "faithfulness": "pass", **outcomes_by_check}

    return Grade.model_validate(
        {"checks": [{"check": check, "outcome": outcome} for check, outcome in checks.items()]}
    )


def a_wrong(fails: str) -> WrongAnswer:
    return WrongAnswer(kind="wrong_rule", fails=fails, answer="A wrong answer.")


def test_stated_facts_and_clean_faithfulness_pass() -> None:
    result = grade_with(YES, YES, YES)

    assert outcomes(result) == {"fact-1": "pass", "fact-2": "pass", "faithfulness": "pass"}
    assert result.fact_score == 1.0


def test_an_unstated_fact_fails_and_halves_the_score() -> None:
    result = grade_with(YES, NO, YES)

    assert outcomes(result)["fact-2"] == "fail"
    assert result.fact_score == 0.5


def test_an_unsupported_claim_fails_faithfulness() -> None:
    result = grade_with(YES, YES, NO)

    assert outcomes(result)["faithfulness"] == "fail"


def test_one_unreadable_reply_is_retried() -> None:
    result = grade_with(UNREADABLE, YES, YES, YES)

    assert outcomes(result) == {"fact-1": "pass", "fact-2": "pass", "faithfulness": "pass"}


def test_code_too_thin_to_judge_leaves_faithfulness_unclear() -> None:
    result = grade_with(YES, YES, UNCLEAR)

    assert outcomes(result)["faithfulness"] == "unclear"


def test_two_unreadable_replies_are_ungraded() -> None:
    result = grade_with(UNREADABLE, UNREADABLE, YES, YES)

    assert outcomes(result)["fact-1"] == "ungraded"
    assert result.fact_score == 0.5


def test_a_clean_correct_answer_is_right() -> None:
    assert outcome_for_correct(a_grade()) == "right"


def test_a_correct_answer_with_a_missed_fact_is_wrong() -> None:
    assert outcome_for_correct(a_grade(**{"fact-1": "fail"})) == "wrong"


def test_a_wrong_answer_failing_its_check_is_right() -> None:
    assert outcome_for_wrong(a_grade(faithfulness="fail"), a_wrong("faithfulness")) == "right"


def test_a_wrong_answer_passing_its_check_is_wrong() -> None:
    assert outcome_for_wrong(a_grade(), a_wrong("fact-2")) == "wrong"


def test_any_ungraded_check_is_inconclusive() -> None:
    result = a_grade(faithfulness="fail", **{"fact-1": "ungraded"})

    assert outcome_for_wrong(result, a_wrong("faithfulness")) == "inconclusive"


def test_an_unclear_check_is_inconclusive_not_right() -> None:
    assert outcome_for_correct(a_grade(faithfulness="unclear")) == "inconclusive"


def test_a_reply_that_is_not_a_verdict_is_ungraded() -> None:
    result = grade(FunctionJudge(reply=lambda prompt: None), QUESTION, "An answer.", "# a.py\n")

    assert set(outcomes(result).values()) == {"ungraded"}


def plain_answers_only(prompt: str) -> Verdict:
    if not prompt.endswith(RETRY_NUDGE):
        raise OutputParserException("not JSON")

    return Verdict(answer="yes")


def test_the_retry_asks_for_a_plain_yes_or_no() -> None:
    result = grade(FunctionJudge(reply=plain_answers_only), QUESTION, "An answer.", "# a.py\n")

    assert outcomes(result)["fact-1"] == "pass"
