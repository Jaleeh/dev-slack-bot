"""The seam a redactor plugs into, and stand-ins that prove the scoring can move."""

from typing import Protocol

from evals.pii_set import PiiSet


class Redactor(Protocol):
    name: str

    def redact(self, text: str) -> str:
        """Returns the text with personal data removed or replaced."""
        ...


class NoRedactor:
    """Leaves the text unchanged, so it catches nothing."""

    name = "none (stand-in)"

    def redact(self, text: str) -> str:
        return text


class AnswerKeyRedactor:
    """Replaces exactly the planted values with <TYPE>, so a working scorer gives it full marks."""

    name = "answer-key"

    def __init__(self, pii_set: PiiSet) -> None:
        self._planted = {snippet.text: snippet.planted for snippet in pii_set.snippets}

    def redact(self, text: str) -> str:
        longest_first = sorted(
            self._planted[text], key=lambda planted: len(planted.value), reverse=True
        )

        for planted in longest_first:
            text = text.replace(planted.value, f"<{planted.type}>")

        return text
