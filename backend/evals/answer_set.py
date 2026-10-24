"""Planted right and wrong answers that show whether the answer grader can be trusted."""

import re
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Annotated, ClassVar, Literal, Self, get_args

from pydantic import AfterValidator, Field, StringConstraints, model_validator

from evals.dataset_file import (
    DatasetModel,
    InvalidDataset,
    Text,
    check_unique_ids,
    load_dataset,
)
from evals.question_set import QuestionSet

ANSWERS_PATH = Path(__file__).parent / "datasets" / "wrong_answers.yaml"

FAITHFULNESS = "faithfulness"
FACT_PREFIX = "fact-"
MAX_CODE_LINES = 80
PATH_LINE = re.compile(r"# [\w./-]+\.\w+")
MIN_USES_PER_KIND = 2

WrongKind = Literal["wrong_rule", "made_up_detail", "vague", "other_question"]
Check = Annotated[str, StringConstraints(pattern=rf"^({FAITHFULNESS}|{FACT_PREFIX}[1-9])$")]


def fact_check(number: int) -> str:
    return f"{FACT_PREFIX}{number}"


def _check_code(code: str) -> str:
    lines = code.splitlines()
    if len(lines) > MAX_CODE_LINES:
        raise ValueError(f"code has more than {MAX_CODE_LINES} lines")
    if not PATH_LINE.fullmatch(lines[0]):
        raise ValueError("code's first line must be '# <path>'")

    return code


class WrongAnswer(DatasetModel):
    kind: WrongKind
    fails: Check
    answer: Text


class AnswerEntry(DatasetModel):
    question_id: Text
    code: Annotated[Text, AfterValidator(_check_code)]
    correct: Text
    wrong: Annotated[tuple[WrongAnswer, ...], Field(min_length=2)]


class AnswerSet(DatasetModel):
    entry_key: ClassVar[str] = "question_id"

    version: Literal[1]
    answers: Annotated[tuple[AnswerEntry, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def _check_unique_ids(self) -> Self:
        check_unique_ids(entry.question_id for entry in self.answers)

        return self

    @model_validator(mode="after")
    def _check_every_kind_is_used(self) -> Self:
        uses = Counter(wrong.kind for entry in self.answers for wrong in entry.wrong)
        rare = [kind for kind in get_args(WrongKind) if uses[kind] < MIN_USES_PER_KIND]
        if rare:
            raise ValueError(f"kinds used fewer than {MIN_USES_PER_KIND} times: {', '.join(rare)}")

        return self


def load_answer_set(path: Path, question_set: QuestionSet) -> AnswerSet:
    """Raises InvalidDataset when an entry breaks the format or doesn't match the question set."""
    answer_set = load_dataset(path, AnswerSet)
    fact_counts = {question.id: len(question.key_facts) for question in question_set.questions}

    problems = tuple(
        problem for entry in answer_set.answers for problem in _mismatches(entry, fact_counts)
    )
    if problems:
        raise InvalidDataset(problems)

    return answer_set


def _mismatches(entry: AnswerEntry, fact_counts: Mapping[str, int]) -> tuple[str, ...]:
    fact_count = fact_counts.get(entry.question_id)
    if fact_count is None:
        return (f"{entry.question_id}: no such question in the question set",)

    return tuple(
        f"{entry.question_id}: {wrong.fails} is past the question's {fact_count} key facts"
        for wrong in entry.wrong
        if wrong.fails != FAITHFULNESS and int(wrong.fails.removeprefix(FACT_PREFIX)) > fact_count
    )
