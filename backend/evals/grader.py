"""Grades an answer with yes/no questions to a judge model, and decides if the grader was right."""

from collections.abc import Sequence
from typing import Literal

from langchain_core.exceptions import OutputParserException
from langchain_core.language_models import BaseChatModel, LanguageModelInput
from langchain_core.runnables import Runnable
from pydantic import BaseModel, ConfigDict, ValidationError

from evals.answer_set import FAITHFULNESS, WrongAnswer, fact_check
from evals.question_set import Question

FACT_PROMPT = """\
You are checking an answer given to a non-technical person about how an online shop works.
Question: {question}
Answer: {answer}
Fact: {fact}
Does the answer state this fact? The wording may differ, but the meaning must match. \
Reply yes or no."""

FAITHFULNESS_PROMPT = """\
You are checking an answer against the shop's code it was based on.
Code:
{code}
Question: {question}
Answer: {answer}
Is every rule, limit, number and behaviour in the answer supported by this code? \
Reply yes or no. Reply unclear if the code shown isn't enough to tell."""

RETRY_NUDGE = "Reply with only the one word asked for."

Reply = Literal["yes", "no", "unclear"]
CheckOutcome = Literal["pass", "fail", "unclear", "ungraded"]
Outcome = Literal["right", "wrong", "inconclusive"]
StructuredJudge = Runnable[LanguageModelInput, object]


class Verdict(BaseModel):
    answer: Literal["yes", "no"]


class FaithfulnessVerdict(BaseModel):
    """Lets the judge say the code shown isn't enough, instead of guessing."""

    answer: Reply


class CheckResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    check: str
    outcome: CheckOutcome


class Grade(BaseModel):
    model_config = ConfigDict(frozen=True)

    checks: tuple[CheckResult, ...]

    @property
    def fact_score(self) -> float:
        return fact_score(self.checks)


def fact_score(checks: Sequence[CheckResult]) -> float:
    """Share of facts stated; an ungraded fact counts as not stated."""
    facts = [check for check in checks if check.check != FAITHFULNESS]

    return sum(check.outcome == "pass" for check in facts) / len(facts)


def grade(judge: BaseChatModel, question: Question, answer: str, code: str) -> Grade:
    """Checks each key fact in order, then faithfulness."""
    structured = judge.with_structured_output(Verdict)
    faithfulness_judge = judge.with_structured_output(FaithfulnessVerdict)
    faithfulness_prompt = FAITHFULNESS_PROMPT.format(
        code=code, question=question.question, answer=answer
    )

    facts = tuple(
        CheckResult(
            check=fact_check(number),
            outcome=_outcome(
                _ask(
                    structured,
                    FACT_PROMPT.format(question=question.question, answer=answer, fact=fact),
                ),
                passing="yes",
            ),
        )
        for number, fact in enumerate(question.key_facts, start=1)
    )
    faithfulness = CheckResult(
        check=FAITHFULNESS,
        outcome=_outcome(_ask(faithfulness_judge, faithfulness_prompt), passing="yes"),
    )

    return Grade(checks=(*facts, faithfulness))


def outcome_for_correct(result: Grade) -> Outcome:
    if _is_inconclusive(result):
        return "inconclusive"

    return "right" if all(check.outcome == "pass" for check in result.checks) else "wrong"


def outcome_for_wrong(result: Grade, wrong: WrongAnswer) -> Outcome:
    if _is_inconclusive(result):
        return "inconclusive"

    outcomes = {check.check: check.outcome for check in result.checks}

    return "right" if outcomes[wrong.fails] == "fail" else "wrong"


def _ask(structured: StructuredJudge, prompt: str) -> FaithfulnessVerdict | None:
    """Retries an unreadable reply once, asking more plainly; None means still unreadable."""
    for attempt in (prompt, f"{prompt}\n{RETRY_NUDGE}"):
        try:
            return FaithfulnessVerdict.model_validate(
                structured.invoke(attempt), from_attributes=True
            )
        # Other providers may return None or a bare dict instead of raising.
        except OutputParserException, ValidationError:
            pass

    return None


def _outcome(verdict: FaithfulnessVerdict | None, passing: Reply) -> CheckOutcome:
    if verdict is None:
        return "ungraded"
    if verdict.answer == "unclear":
        return "unclear"

    return "pass" if verdict.answer == passing else "fail"


def _is_inconclusive(result: Grade) -> bool:
    return any(check.outcome in ("unclear", "ungraded") for check in result.checks)
