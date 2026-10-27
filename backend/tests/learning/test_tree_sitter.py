"""Pins how tree-sitter-language-pack outlines code for the outline search tool."""

import pytest
from tree_sitter_language_pack import (
    DownloadError,
    ProcessConfig,
    StructureItem,
    detect_language_from_path,
    process,
)

BASKET = "class Basket:\n    def merge(self):\n        pass\n"


def structure(source: str, language: str) -> list[StructureItem]:
    return process(source, ProcessConfig(language=language, structure=True)).structure


@pytest.mark.usefixtures("grammars")
def test_structure_lists_a_python_class_with_its_method_as_a_child() -> None:
    items = structure(BASKET, "python")

    assert len(items) == 1
    assert items[0].name == "Basket"
    assert "Class" in str(items[0].kind)
    assert items[0].children[0].name == "merge"


@pytest.mark.usefixtures("grammars")
def test_structure_lines_are_zero_based() -> None:
    basket = structure(BASKET, "python")[0]
    merge = basket.children[0]

    assert basket.span and basket.span.start_line == 0
    assert merge.span and merge.span.start_line == 1


@pytest.mark.usefixtures("grammars")
def test_structure_lists_a_typescript_method() -> None:
    items = structure("export class Offer { apply(x: number) { return x } }", "typescript")

    assert items[0].children[0].name == "apply"


def test_unknown_extension_has_no_language() -> None:
    assert detect_language_from_path("data.xyz") is None


def test_unknown_language_raises_download_error() -> None:
    with pytest.raises(DownloadError):
        structure("x", "nosuchlang")


@pytest.mark.usefixtures("grammars")
def test_broken_code_still_yields_structure() -> None:
    items = structure("def broken(:\n  pass\n", "python")

    assert [item.name for item in items] == ["broken"]
