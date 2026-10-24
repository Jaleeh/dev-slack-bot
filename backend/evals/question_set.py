"""The labelled question set that retrieval and answers are scored against."""

from pathlib import Path, PurePosixPath
from typing import Annotated, Literal, Self

from pydantic import AfterValidator, Field, model_validator

from evals.dataset_file import DatasetModel, Text, check_unique_ids, load_dataset

QUESTIONS_PATH = Path(__file__).parent / "datasets" / "questions.yaml"

# Developer-speak makes a question test grep rather than understanding.
CODE_MARKERS = ("_", "`", ".py", "()")


def _check_repo_path(path: str) -> str:
    pure = PurePosixPath(path)
    if "\\" in path:
        raise ValueError(f"{path} uses backslashes")
    if pure.is_absolute():
        raise ValueError(f"{path} is absolute")
    if ".." in pure.parts:
        raise ValueError(f"{path} climbs out of the repository")
    if pure.as_posix() != path:
        raise ValueError(f"{path} is not normalised")
    if path == ".":
        raise ValueError("'.' is not a file")

    return path


def _check_plain_wording(question: str) -> str:
    named = [marker for marker in CODE_MARKERS if marker in question]
    if named:
        raise ValueError(f"question names code ({', '.join(named)})")

    return question


RepoPath = Annotated[Text, AfterValidator(_check_repo_path)]


class Question(DatasetModel):
    id: Text
    type: Literal["how_it_works", "bug_or_setup"]
    question: Annotated[Text, AfterValidator(_check_plain_wording)]
    key_facts: Annotated[tuple[Text, ...], Field(min_length=2, max_length=5)]
    files: Annotated[tuple[RepoPath, ...], Field(min_length=1, max_length=4)]


class QuestionSet(DatasetModel):
    version: Literal[1]
    repo: Text
    ref: Text
    questions: Annotated[tuple[Question, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def _check_unique_ids(self) -> Self:
        check_unique_ids(question.id for question in self.questions)

        return self


def load_question_set(path: Path) -> QuestionSet:
    return load_dataset(path, QuestionSet)
