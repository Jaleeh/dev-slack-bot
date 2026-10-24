"""Loads a YAML eval dataset into its model, naming each bad entry by id."""

from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import Annotated, Any, ClassVar

import yaml
from pydantic import BaseModel, ConfigDict, StringConstraints, ValidationError

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class DatasetModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    # The field that names an entry in error messages.
    entry_key: ClassVar[str] = "id"


class InvalidDataset(ValueError):
    """A dataset file broke the format; each problem names its entry by id."""

    def __init__(self, problems: tuple[str, ...]) -> None:
        super().__init__("\n".join(problems))
        self.problems = problems


def check_unique_ids(ids: Iterable[str]) -> None:
    duplicates = sorted(id_ for id_, count in Counter(ids).items() if count > 1)
    if duplicates:
        raise ValueError(f"duplicated ids: {', '.join(duplicates)}")


def load_dataset[DatasetT: DatasetModel](path: Path, model: type[DatasetT]) -> DatasetT:
    """Raises InvalidDataset on a format problem, yaml.YAMLError on unparseable YAML."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))

    try:
        return model.model_validate(data)
    except ValidationError as error:
        problems = tuple(_describe(problem, data, model) for problem in error.errors())
        raise InvalidDataset(problems) from error


def _describe(problem: Any, data: Any, model: type[DatasetModel]) -> str:
    location = ".".join(str(part) for part in problem["loc"])

    match problem["loc"]:
        case (str(key), int(index), *_):
            name = _entry_name(data[key][index], index, model.entry_key)
            return f"{name} ({location}): {problem['msg']}"
        case _:
            return f"{location}: {problem['msg']}"


def _entry_name(entry: Any, index: int, key: str) -> str:
    if isinstance(entry, dict) and entry.get(key):
        return str(entry[key])

    return f"entry {index + 1}"
