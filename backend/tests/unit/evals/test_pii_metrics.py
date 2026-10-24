from typing import Any

from evals.pii_metrics import pii_metrics, score_snippet
from evals.pii_set import PiiType, Snippet

SPEC_QUESTION = "Why can't John Doe (john.doe@example.com, 07700 900123) check out?"
JOHN = {"type": "PERSON", "value": "John Doe"}
EMAIL = {"type": "EMAIL", "value": "john.doe@example.com"}
PHONE = {"type": "PHONE", "value": "07700 900123"}


def a_snippet(**overrides: Any) -> Snippet:
    return Snippet.model_validate(
        {
            "id": "s1",
            "kind": "question",
            "text": SPEC_QUESTION,
            "planted": [JOHN, EMAIL, PHONE],
            "lookalikes": [],
            **overrides,
        }
    )


def missed_values(snippet: Snippet, redacted: str) -> tuple[str, ...]:
    return tuple(planted.value for planted in score_snippet(snippet, redacted).missed)


def test_unchanged_text_catches_nothing() -> None:
    snippet = a_snippet()

    result = score_snippet(snippet, SPEC_QUESTION)

    assert pii_metrics([snippet], [result]).catch_rate == 0.0
    assert result.missed == snippet.planted


def test_removing_every_value_catches_all() -> None:
    snippet = a_snippet()

    result = score_snippet(snippet, "Why can't <PERSON> (<EMAIL>, <PHONE>) check out?")

    assert pii_metrics([snippet], [result]).catch_rate == 1.0
    assert result.missed == ()


def test_a_leftover_first_name_is_a_miss() -> None:
    redacted = "Why can't John <PERSON> (<EMAIL>, <PHONE>) check out?"

    assert missed_values(a_snippet(), redacted) == ("John Doe",)


def test_a_name_word_inside_a_longer_word_is_a_miss() -> None:
    snippet = a_snippet(
        text="Ask Jo Doe about it.", planted=[{"type": "PERSON", "value": "Jo Doe"}]
    )

    assert missed_values(snippet, "Ask Doesn't know about it.") == ("Jo Doe",)


def test_a_phone_fragment_left_behind_still_counts_as_caught() -> None:
    redacted = "Why can't <PERSON> (<EMAIL>, 07700 <PHONE>) check out?"

    assert missed_values(a_snippet(), redacted) == ()


def test_a_value_still_in_the_text_once_is_a_miss() -> None:
    snippet = a_snippet(
        text="Mail john.doe@example.com, or john.doe@example.com again.", planted=[EMAIL]
    )

    redacted = "Mail <EMAIL>, or john.doe@example.com again."

    assert missed_values(snippet, redacted) == ("john.doe@example.com",)


def test_a_removed_lookalike_is_wrongly_flagged() -> None:
    snippet = a_snippet(text="Order 100042 for John Doe.", planted=[JOHN], lookalikes=["100042"])

    result = score_snippet(snippet, "Order <ID> for <PERSON>.")

    assert result.wrongly_flagged == ("100042",)
    assert pii_metrics([snippet], [result]).wrong_flag_rate == 1.0


def test_a_kept_lookalike_is_not_flagged() -> None:
    snippet = a_snippet(text="Order 100042 for John Doe.", planted=[JOHN], lookalikes=["100042"])

    result = score_snippet(snippet, "Order 100042 for <PERSON>.")

    assert pii_metrics([snippet], [result]).wrong_flag_rate == 0.0


def test_catch_rate_is_counted_per_type() -> None:
    snippet = a_snippet(
        text="John Doe and Jane Roe wrote from john.doe@example.com.",
        planted=[JOHN, {"type": "PERSON", "value": "Jane Roe"}, EMAIL],
    )

    result = score_snippet(snippet, "<PERSON> and Jane Roe wrote from <EMAIL>.")

    metrics = pii_metrics([snippet], [result])
    assert metrics.catch_rate_by_type == {PiiType.PERSON: 0.5, PiiType.EMAIL: 1.0}
    assert metrics.catch_rate == 2 / 3


def test_wrong_flag_rate_is_none_without_lookalikes() -> None:
    snippet = a_snippet()

    result = score_snippet(snippet, SPEC_QUESTION)

    assert pii_metrics([snippet], [result]).wrong_flag_rate is None
