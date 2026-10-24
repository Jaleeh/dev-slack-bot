from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from evals.answer_set import ANSWERS_PATH, AnswerSet, load_answer_set
from evals.dataset_file import InvalidDataset
from evals.question_set import QUESTIONS_PATH, QuestionSet, load_question_set
from tests.answer_datasets import (
    CODE,
    EVERY_KIND,
    a_question,
    a_question_set,
    a_wrong,
    an_answer_set,
    an_entry,
)

QUESTION_SET = QuestionSet.model_validate(a_question_set(a_question("q1", 3), a_question("q2", 2)))


VALID_SET = an_answer_set(an_entry(), an_entry(question_id="q2"))


def write(tmp_path: Path, data: dict[str, Any]) -> Path:
    path = tmp_path / "wrong_answers.yaml"
    path.write_text(yaml.safe_dump(data))

    return path


def test_a_valid_set_loads(tmp_path: Path) -> None:
    answer_set = load_answer_set(write(tmp_path, VALID_SET), QUESTION_SET)

    assert len(answer_set.answers) == 2


def test_an_unknown_question_is_rejected(tmp_path: Path) -> None:
    data = an_answer_set(an_entry(), an_entry(question_id="no-such-question"))

    with pytest.raises(InvalidDataset, match="no-such-question"):
        load_answer_set(write(tmp_path, data), QUESTION_SET)


def test_a_fact_number_past_the_last_fact_is_rejected(tmp_path: Path) -> None:
    past_the_end = [*EVERY_KIND, a_wrong("wrong_rule", "fact-4")]
    data = an_answer_set(an_entry(wrong=past_the_end), an_entry(question_id="q2"))

    with pytest.raises(InvalidDataset, match="q1: fact-4"):
        load_answer_set(write(tmp_path, data), QUESTION_SET)


def test_a_bad_entry_is_named_by_its_question(tmp_path: Path) -> None:
    data = an_answer_set(an_entry(), an_entry(question_id="q2", correct=" "))

    with pytest.raises(InvalidDataset, match=r"q2 \(answers\.1"):
        load_answer_set(write(tmp_path, data), QUESTION_SET)


@pytest.mark.parametrize(
    ("entry", "match"),
    [
        pytest.param(
            an_entry(wrong=[*EVERY_KIND, a_wrong("vague", "tone")]),
            r"answers\.0\.wrong\.4\.fails",
            id="unknown check",
        ),
        pytest.param(
            an_entry(code=CODE + "x = 1\n" * 78),
            "more than 80 lines",
            id="code over 80 lines",
        ),
        pytest.param(
            an_entry(code="# Offers are applied in priority order.\nclass Offer:\n    pass\n"),
            "first line must be '# <path>'",
            id="code starting with a comment",
        ),
        pytest.param(
            an_entry(code="class Offer:\n    pass\n"),
            "first line must be '# <path>'",
            id="code without a path line",
        ),
        pytest.param(
            an_entry(wrong=[a_wrong("vague", "fact-1")]),
            r"answers\.0\.wrong\s",
            id="one wrong answer",
        ),
    ],
)
def test_a_bad_entry_is_rejected(entry: dict[str, Any], match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        AnswerSet.model_validate(an_answer_set(entry, an_entry(question_id="q2")))


def test_a_repeated_question_is_rejected() -> None:
    with pytest.raises(ValidationError, match="duplicated ids: q1"):
        AnswerSet.model_validate(an_answer_set(an_entry(), an_entry()))


def test_a_kind_used_once_is_rejected() -> None:
    without_vague = [wrong for wrong in EVERY_KIND if wrong["kind"] != "vague"]

    with pytest.raises(ValidationError, match="used fewer than 2 times: vague"):
        AnswerSet.model_validate(
            an_answer_set(an_entry(), an_entry(question_id="q2", wrong=without_vague))
        )


def test_the_planted_answer_set_loads() -> None:
    answer_set = load_answer_set(ANSWERS_PATH, load_question_set(QUESTIONS_PATH))

    assert len(answer_set.answers) == 10
