"""The labelled question set that retrieval and answers are scored against."""

from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Annotated, Any, Literal, Self

import yaml
from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    model_validator,
)

QUESTIONS_PATH = Path(__file__).parent / "datasets" / "questions.yaml"

# Developer-speak makes a question test grep rather than understanding.
CODE_MARKERS = ("_", "`", ".py", "()")


class InvalidQuestionSet(ValueError):
    """A question set file broke the format; each problem names its entry by id."""

    def __init__(self, problems: tuple[str, ...]) -> None:
        super().__init__("\n".join(problems))
        self.problems = problems


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


Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
RepoPath = Annotated[Text, AfterValidator(_check_repo_path)]


class Question(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: Text
    type: Literal["how_it_works", "bug_or_setup"]
    question: Annotated[Text, AfterValidator(_check_plain_wording)]
    key_facts: Annotated[tuple[Text, ...], Field(min_length=2, max_length=5)]
    files: Annotated[tuple[RepoPath, ...], Field(min_length=1, max_length=4)]


class QuestionSet(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: Literal[1]
    repo: Text
    ref: Text
    questions: Annotated[tuple[Question, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def _check_unique_ids(self) -> Self:
        counts = Counter(question.id for question in self.questions)
        duplicates = sorted(id_ for id_, count in counts.items() if count > 1)
        if duplicates:
            raise ValueError(f"duplicated ids: {', '.join(duplicates)}")

        return self


def load_question_set(path: Path) -> QuestionSet:
    """Raises InvalidQuestionSet on a format problem, yaml.YAMLError on unparseable YAML."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))

    try:
        return QuestionSet.model_validate(data)
    except ValidationError as error:
        problems = tuple(_describe(problem, data) for problem in error.errors())
        raise InvalidQuestionSet(problems) from error


def _describe(problem: Any, data: Any) -> str:
    location = ".".join(str(part) for part in problem["loc"])

    match problem["loc"]:
        case ("questions", int(index), *_):
            return f"{_entry_name(data, index)} ({location}): {problem['msg']}"
        case _:
            return f"{location}: {problem['msg']}"


def _entry_name(data: Any, index: int) -> str:
    entry = data["questions"][index]
    if isinstance(entry, dict) and entry.get("id"):
        return str(entry["id"])

    return f"entry {index + 1}"
