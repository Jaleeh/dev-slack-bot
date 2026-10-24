from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from evals.question_set import (
    QUESTIONS_PATH,
    InvalidQuestionSet,
    QuestionSet,
    load_question_set,
)

OFFER_FILE = "src/oscar/apps/offer/applicator.py"


def a_question(**overrides: Any) -> dict[str, Any]:
    return {
        "id": "q1",
        "type": "how_it_works",
        "question": "Which discount applies first when a voucher and a sale both apply?",
        "key_facts": ["Higher priority promotions apply first.", "Priority defaults to 0."],
        "files": [OFFER_FILE],
        **overrides,
    }


def a_question_set(*questions: dict[str, Any]) -> dict[str, Any]:
    return {"version": 1, "repo": "django-oscar", "ref": "4.2.1", "questions": list(questions)}


def test_a_valid_set_loads() -> None:
    question_set = QuestionSet.model_validate(a_question_set(a_question()))

    assert question_set.questions[0].files == (OFFER_FILE,)


def test_loaded_questions_cannot_be_changed() -> None:
    question_set = QuestionSet.model_validate(a_question_set(a_question()))

    with pytest.raises(ValidationError):
        question_set.questions[0].id = "x"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("overrides", "match"),
    [
        pytest.param({"id": "  "}, r"questions\.0\.id\s", id="blank id"),
        pytest.param({"type": "trivia"}, r"questions\.0\.type\s", id="unknown type"),
        pytest.param({"key_facts": []}, r"questions\.0\.key_facts\s", id="no key facts"),
        pytest.param(
            {"key_facts": ["A fact.", ""]}, r"questions\.0\.key_facts\.1\s", id="blank key fact"
        ),
        pytest.param({"files": []}, r"questions\.0\.files\s", id="no files"),
        pytest.param({"files": ["/src/a.py"]}, r"/src/a\.py is absolute", id="absolute path"),
        pytest.param({"files": ["src/../a.py"]}, r"src/\.\./a\.py climbs out", id="climbs out"),
        pytest.param({"files": ["./src/a.py"]}, r"\./src/a\.py is not normal", id="not normalised"),
        pytest.param({"question": "What does apply_offers do?"}, r"names code \(_\)", id="_"),
        pytest.param({"question": "What does `Basket` do?"}, r"names code \(`\)", id="backtick"),
        pytest.param({"question": "What is in views.py?"}, r"names code \(\.py\)", id=".py"),
        pytest.param({"question": "What does apply() do?"}, r"names code \(\(\)\)", id="()"),
        pytest.param({"file": ["src/a.py"]}, r"questions\.0\.file\s", id="unknown key"),
        pytest.param({"key_facts": ["One fact."]}, r"questions\.0\.key_facts\s", id="1 fact"),
        pytest.param({"key_facts": ["A."] * 6}, r"questions\.0\.key_facts\s", id="6 facts"),
        pytest.param({"files": [OFFER_FILE] * 5}, r"questions\.0\.files\s", id="5 files"),
        pytest.param({"files": ["."]}, r"'\.' is not a file", id="dot path"),
        pytest.param({"files": ["src\\a.py"]}, r"uses backslashes", id="backslash path"),
    ],
)
def test_rejects_a_bad_question(overrides: dict[str, Any], match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        QuestionSet.model_validate(a_question_set(a_question(**overrides)))


def test_rejects_a_missing_id() -> None:
    question = a_question()
    del question["id"]

    with pytest.raises(ValidationError, match=r"questions\.0\.id\s"):
        QuestionSet.model_validate(a_question_set(question))


def test_rejects_a_duplicated_id() -> None:
    with pytest.raises(ValidationError, match="duplicated ids: q1"):
        QuestionSet.model_validate(a_question_set(a_question(), a_question()))


def test_rejects_an_empty_question_list() -> None:
    with pytest.raises(ValidationError, match=r"questions\s"):
        QuestionSet.model_validate(a_question_set())


def test_rejects_an_unknown_version() -> None:
    with pytest.raises(ValidationError, match=r"version\s"):
        QuestionSet.model_validate({**a_question_set(a_question()), "version": 2})


def test_load_names_a_bad_entry_by_its_id(tmp_path: Path) -> None:
    path = tmp_path / "questions.yaml"
    path.write_text(yaml.safe_dump(a_question_set(a_question(id="voucher-dates", files=["./a"]))))

    with pytest.raises(InvalidQuestionSet, match=r"voucher-dates \(questions\.0\.files\.0\)"):
        load_question_set(path)


def test_load_names_an_entry_without_an_id_by_its_position(tmp_path: Path) -> None:
    question = a_question()
    del question["id"]
    path = tmp_path / "questions.yaml"
    path.write_text(yaml.safe_dump(a_question_set(question)))

    with pytest.raises(InvalidQuestionSet, match=r"entry 1 \(questions\.0\.id\)"):
        load_question_set(path)


def test_rejects_a_top_level_that_is_not_a_mapping() -> None:
    with pytest.raises(ValidationError):
        QuestionSet.model_validate(None)


def test_load_reads_a_yaml_file(tmp_path: Path) -> None:
    path = tmp_path / "questions.yaml"
    path.write_text(yaml.safe_dump(a_question_set(a_question())))

    assert load_question_set(path).repo == "django-oscar"


def test_the_oscar_question_set_is_valid() -> None:
    question_set = load_question_set(QUESTIONS_PATH)

    assert (question_set.repo, question_set.ref) == ("django-oscar", "4.2.1")
