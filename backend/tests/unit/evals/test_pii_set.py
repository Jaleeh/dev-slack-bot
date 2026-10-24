from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from evals.dataset_file import InvalidDataset
from evals.pii_set import PII_PATH, PiiSet, PiiType, load_pii_set, name_words

SPEC_QUESTION = "Why can't John Doe (john.doe@example.com, 07700 900123) check out?"


def planted(type_: str, value: str) -> dict[str, str]:
    return {"type": type_, "value": value}


def a_snippet(**overrides: Any) -> dict[str, Any]:
    return {
        "id": "s1",
        "kind": "question",
        "text": SPEC_QUESTION,
        "planted": [
            planted("PERSON", "John Doe"),
            planted("EMAIL", "john.doe@example.com"),
            planted("PHONE", "07700 900123"),
        ],
        "lookalikes": [],
        **overrides,
    }


def a_snippet_planting(type_: str, value: str) -> dict[str, Any]:
    return a_snippet(text=f"Ask about {value} please.", planted=[planted(type_, value)])


def a_pii_set(*snippets: dict[str, Any]) -> dict[str, Any]:
    return {"version": 1, "snippets": list(snippets)}


def test_the_spec_example_loads() -> None:
    pii_set = PiiSet.model_validate(a_pii_set(a_snippet()))

    assert pii_set.snippets[0].planted[0].type is PiiType.PERSON


def test_accepts_every_fake_source() -> None:
    values = [
        planted("PHONE", "+44 7700 900123"),
        planted("PHONE", "020 7946 0123"),
        planted("PHONE", "+44 20 7946 0999"),
        planted("UK_NINO", "QQ 12 34 56 C"),
        planted("CARD", "4111 1111 1111 1111"),
        planted("IP", "198.51.100.7"),
        planted("EMAIL", "jane@example.net"),
    ]
    text = " | ".join(value["value"] for value in values)

    pii_set = PiiSet.model_validate(a_pii_set(a_snippet(text=text, planted=values)))

    assert len(pii_set.snippets[0].planted) == len(values)


def test_a_lookalike_outside_the_value_is_allowed() -> None:
    settings_file = a_snippet(
        id="settings-file",
        kind="code",
        text='ALLOWED_HOSTS = ["example.com"]\nSUPPORT_EMAIL = "jane.roe@example.com"\n',
        planted=[planted("EMAIL", "jane.roe@example.com")],
        lookalikes=['["example.com"]', "ALLOWED_HOSTS"],
    )

    pii_set = PiiSet.model_validate(a_pii_set(settings_file))

    assert pii_set.snippets[0].lookalikes == ('["example.com"]', "ALLOWED_HOSTS")


def test_a_name_inside_another_planted_value_is_allowed() -> None:
    snippet = a_snippet(
        text="John Doe <John.Doe@example.com>",
        planted=[planted("PERSON", "John Doe"), planted("EMAIL", "John.Doe@example.com")],
    )

    pii_set = PiiSet.model_validate(a_pii_set(snippet))

    assert len(pii_set.snippets[0].planted) == 2


def test_accepts_a_nino_without_spaces() -> None:
    pii_set = PiiSet.model_validate(a_pii_set(a_snippet_planting("UK_NINO", "QQ123456C")))

    assert pii_set.snippets[0].planted[0].value == "QQ123456C"


def test_loaded_snippets_cannot_be_changed() -> None:
    pii_set = PiiSet.model_validate(a_pii_set(a_snippet()))

    with pytest.raises(ValidationError):
        pii_set.snippets[0].id = "x"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("snippet", "match"),
    [
        pytest.param(
            a_snippet(planted=[planted("PASSPORT", "John Doe")]),
            r"snippets\.0\.planted\.0\.type\s",
            id="unknown type",
        ),
        pytest.param(a_snippet(kind="email"), r"snippets\.0\.kind\s", id="unknown kind"),
        pytest.param(
            a_snippet(planted_values=[]), r"snippets\.0\.planted_values\s", id="unknown key"
        ),
        pytest.param(a_snippet(text="  "), r"snippets\.0\.text\s", id="blank text"),
        pytest.param(
            a_snippet(planted=[planted("EMAIL", "jane.roe@example.com")]),
            r"'jane\.roe@example\.com' is not in the text",
            id="value not in text",
        ),
        pytest.param(
            a_snippet(lookalikes=["user_email"]),
            r"'user_email' is not in the text outside planted values",
            id="look-alike not in text",
        ),
        pytest.param(
            a_snippet(lookalikes=["example.com"]),
            r"'example\.com' is not in the text outside planted values",
            id="look-alike only inside a value",
        ),
        pytest.param(
            a_snippet(
                text="Hosts: example.com. Mail jane.roe@example.com.",
                planted=[planted("EMAIL", "jane.roe@example.com")],
                lookalikes=["example.com"],
            ),
            r"'example\.com' appears more than once in the text",
            id="look-alike also inside a value",
        ),
        pytest.param(
            a_snippet(
                text="Hits from 192.0.2.20 and 192.0.2.200.",
                planted=[planted("IP", "192.0.2.20"), planted("IP", "192.0.2.200")],
            ),
            r"'192\.0\.2\.20' overlaps another planted value",
            id="value is part of another value",
        ),
        pytest.param(
            a_snippet(
                text="John Doe paid on 2 Oct and again on 2 Oct.",
                planted=[planted("PERSON", "John Doe")],
                lookalikes=["2 Oct"],
            ),
            r"'2 Oct' appears more than once in the text",
            id="look-alike repeated",
        ),
        pytest.param(
            a_snippet(
                text="John Doe says John is locked out.", planted=[planted("PERSON", "John Doe")]
            ),
            r"'John' from 'John Doe' also appears elsewhere",
            id="name word reused",
        ),
        pytest.param(
            a_snippet(text="Ask John Doe about Doecraft.", planted=[planted("PERSON", "John Doe")]),
            r"'Doe' from 'John Doe' also appears elsewhere",
            id="name word inside a word",
        ),
        pytest.param(
            a_snippet(
                text="Send it to 12 Acacia Avenue, not Acacia Court.",
                planted=[planted("ADDRESS", "12 Acacia Avenue")],
            ),
            r"'Acacia' from '12 Acacia Avenue'",
            id="address word reused",
        ),
        pytest.param(
            a_snippet(planted=[planted("PERSON", "John Doe"), planted("PERSON", "John Doe")]),
            r"'John Doe' is planted twice",
            id="planted twice",
        ),
        pytest.param(
            a_snippet(planted=[], lookalikes=[]),
            r"nothing planted and no look-alikes",
            id="empty snippet",
        ),
        pytest.param(
            a_snippet_planting("EMAIL", "x@gmail.com"),
            r"'x@gmail\.com' is not at a reserved example domain",
            id="real email domain",
        ),
        pytest.param(
            a_snippet_planting("PHONE", "07700 123456"),
            r"'07700 123456' is not in an Ofcom drama range",
            id="real phone",
        ),
        pytest.param(
            a_snippet_planting("UK_NINO", "AB 12 34 56 C"),
            r"'AB 12 34 56 C' is not a QQ National Insurance number",
            id="issued NINO prefix",
        ),
        pytest.param(
            a_snippet_planting("UK_NINO", "QQ hello"),
            r"'QQ hello' is not a QQ National Insurance number",
            id="QQ but not a NINO",
        ),
        pytest.param(
            a_snippet_planting("EMAIL", "example.com"),
            r"'example\.com' is not at a reserved example domain",
            id="email without @",
        ),
        pytest.param(
            a_snippet_planting("EMAIL", "x@gmail.com@example.com"),
            r"'x@gmail\.com@example\.com' is not at a reserved example domain",
            id="email with two @",
        ),
        pytest.param(
            a_snippet(
                text="Ask Kwame Ashbury Close about it.",
                planted=[planted("PERSON", "Kwame Ashbury"), planted("ADDRESS", "Ashbury Close")],
            ),
            r"'Kwame Ashbury' overlaps another planted value",
            id="planted values overlap",
        ),
        pytest.param(
            a_snippet(
                text="Please check out now.", planted=[], lookalikes=["check out", "check out"]
            ),
            r"'check out' is a look-alike twice",
            id="look-alike twice",
        ),
        pytest.param(
            a_snippet_planting("CARD", "4111 1111 1111 1112"),
            r"'4111 1111 1111 1112' is not a published test card",
            id="card not on the published list",
        ),
        pytest.param(
            a_snippet_planting("CARD", "4000 0000 0000 0002"),
            r"'4000 0000 0000 0002' is not a published test card",
            id="card passes Luhn but is not on the list",
        ),
        pytest.param(
            a_snippet_planting("IP", "8.8.8.8"),
            r"'8\.8\.8\.8' is not in an RFC 5737 range",
            id="public IP",
        ),
        pytest.param(
            a_snippet_planting("IP", "192.0.2"),
            r"'192\.0\.2' is not in an RFC 5737 range",
            id="not an IP",
        ),
    ],
)
def test_rejects_a_bad_snippet(snippet: dict[str, Any], match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        PiiSet.model_validate(a_pii_set(snippet))


def test_rejects_a_duplicated_id() -> None:
    with pytest.raises(ValidationError, match="duplicated ids: s1"):
        PiiSet.model_validate(a_pii_set(a_snippet(), a_snippet()))


def test_rejects_no_snippets() -> None:
    with pytest.raises(ValidationError, match=r"snippets\s"):
        PiiSet.model_validate(a_pii_set())


def test_name_words_keeps_words_of_three_letters_or_more() -> None:
    assert name_words("Jo Ann O'Brien-Smith, 12 Élan Road") == (
        "Ann",
        "Brien",
        "Smith",
        "Élan",
        "Road",
    )


def test_load_names_a_bad_snippet_by_its_id(tmp_path: Path) -> None:
    snippet = a_snippet(id="refund-call", planted=[planted("EMAIL", "jane.roe@example.com")])
    path = tmp_path / "pii.yaml"
    path.write_text(yaml.safe_dump(a_pii_set(snippet)))

    with pytest.raises(InvalidDataset, match=r"refund-call \(snippets\.0\)"):
        load_pii_set(path)


def test_the_pii_set_is_valid() -> None:
    pii_set = load_pii_set(PII_PATH)

    planted_types = {planted.type for snippet in pii_set.snippets for planted in snippet.planted}
    assert len(pii_set.snippets) >= 20
    assert planted_types == set(PiiType)
