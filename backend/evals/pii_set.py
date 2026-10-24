"""The fake personal data set that redactors are scored against."""

import ipaddress
import re
from collections import Counter
from collections.abc import Iterable
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from evals.dataset_file import DatasetModel, Text, check_unique_ids, load_dataset

PII_PATH = Path(__file__).parent / "datasets" / "pii.yaml"

# RFC 2606 reserves these domains for examples.
EXAMPLE_EMAIL = re.compile(r"[^@\s]+@example\.(?:com|org|net)")
# HMRC never issues the QQ prefix.
TEST_NINO = re.compile(r"QQ ?\d{2} ?\d{2} ?\d{2} ?[A-D]")
# Ofcom keeps these mobile and London numbers free for drama and examples.
DRAMA_PHONE = re.compile(r"07700900\d{3}|02079460\d{3}")
DOCUMENTATION_NETWORKS = tuple(
    ipaddress.ip_network(network)
    for network in ("192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24")
)
# Published by card networks for testing; each passes Luhn, so detectors treat it as real.
TEST_CARDS = frozenset(
    {"4111111111111111", "4242424242424242", "5555555555554444", "378282246310005"}
)
NAME_WORD = re.compile(r"[^\W\d_]{3,}")
# No value contains it, so masked gaps can't join into new words.
MASK = "\x00"


class PiiType(StrEnum):
    PERSON = "PERSON"
    EMAIL = "EMAIL"
    PHONE = "PHONE"
    UK_NINO = "UK_NINO"
    CARD = "CARD"
    IP = "IP"
    SECRET = "SECRET"
    ADDRESS = "ADDRESS"
    DATE_OF_BIRTH = "DATE_OF_BIRTH"


# A leftover word of these still identifies someone, so each word must go.
NAMED_TYPES = frozenset({PiiType.PERSON, PiiType.ADDRESS})


def name_words(value: str) -> tuple[str, ...]:
    """The words of 3 or more letters, which a redactor must remove one by one."""
    return tuple(NAME_WORD.findall(value))


class PlantedValue(DatasetModel):
    type: PiiType
    value: Text

    @model_validator(mode="after")
    def _check_fake_source(self) -> Self:
        problem = _fake_source_problem(self.type, self.value)
        if problem:
            raise ValueError(f"{self.value!r} {problem}")

        return self


class Snippet(DatasetModel):
    id: Text
    kind: Literal["question", "code"]
    text: Text
    planted: tuple[PlantedValue, ...]
    lookalikes: tuple[Text, ...]

    @model_validator(mode="after")
    def _check_text(self) -> Self:
        problems = _text_problems(self)
        if problems:
            raise ValueError("; ".join(problems))

        return self


class PiiSet(DatasetModel):
    version: Literal[1]
    snippets: Annotated[tuple[Snippet, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def _check_unique_ids(self) -> Self:
        check_unique_ids(snippet.id for snippet in self.snippets)

        return self


def load_pii_set(path: Path) -> PiiSet:
    return load_dataset(path, PiiSet)


def _fake_source_problem(type_: PiiType, value: str) -> str | None:
    match type_:
        case PiiType.EMAIL if not EXAMPLE_EMAIL.fullmatch(value):
            return "is not at a reserved example domain"
        case PiiType.PHONE if not DRAMA_PHONE.fullmatch(_uk_national_digits(value)):
            return "is not in an Ofcom drama range"
        case PiiType.UK_NINO if not TEST_NINO.fullmatch(value):
            return "is not a QQ National Insurance number"
        case PiiType.CARD if value.replace(" ", "") not in TEST_CARDS:
            return "is not a published test card"
        case PiiType.IP if not _is_documentation_ip(value):
            return "is not in an RFC 5737 range"
        case _:
            return None


def _uk_national_digits(phone: str) -> str:
    digits = phone.replace(" ", "")

    return "0" + digits[3:] if digits.startswith("+44") else digits


def _is_documentation_ip(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False

    return any(address in network for network in DOCUMENTATION_NETWORKS)


def _text_problems(snippet: Snippet) -> tuple[str, ...]:
    if not snippet.planted and not snippet.lookalikes:
        return ("nothing planted and no look-alikes",)

    values = [planted.value for planted in snippet.planted]
    outside = _mask(snippet.text, values)

    return (
        *(f"{value!r} is not in the text" for value in values if value not in snippet.text),
        *(f"{value!r} is planted twice" for value in _repeated(values)),
        *(
            f"{value!r} overlaps another planted value"
            for value in _overlapping(values, snippet.text)
        ),
        *(f"{lookalike!r} is a look-alike twice" for lookalike in _repeated(snippet.lookalikes)),
        *(
            f"{lookalike!r} is not in the text outside planted values"
            for lookalike in snippet.lookalikes
            if lookalike not in outside
        ),
        # Scoring checks a look-alike is still in the output, so one copy must be all there is.
        *(
            f"{lookalike!r} appears more than once in the text"
            for lookalike in snippet.lookalikes
            if snippet.text.count(lookalike) > 1
        ),
        *_reused_name_words(snippet, outside),
    )


def _mask(text: str, values: Iterable[str]) -> str:
    longest_first = sorted(values, key=len, reverse=True)

    for value in longest_first:
        text = text.replace(value, MASK)

    return text


def _repeated(items: Iterable[str]) -> tuple[str, ...]:
    return tuple(item for item, count in Counter(items).items() if count > 1)


def _overlapping(values: list[str], text: str) -> tuple[str, ...]:
    """Values inside or sharing text with another, which scoring couldn't tell apart."""
    distinct = dict.fromkeys(values)

    return tuple(value for value in distinct if _overlaps_another(value, distinct, text))


def _overlaps_another(value: str, distinct: Iterable[str], text: str) -> bool:
    others = [other for other in distinct if other != value]
    if any(value in other for other in others):
        return True

    return value in text and value not in _mask(text, others)


def _reused_name_words(snippet: Snippet, outside: str) -> tuple[str, ...]:
    return tuple(
        f"{word!r} from {planted.value!r} also appears elsewhere in the text"
        for planted in snippet.planted
        if planted.type in NAMED_TYPES
        for word in name_words(planted.value)
        if word in outside
    )
