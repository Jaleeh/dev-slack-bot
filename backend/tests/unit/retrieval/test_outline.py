from pathlib import Path

import pytest

from app.retrieval.direct.errors import CannotOutline, NotText
from app.retrieval.direct.outline import Symbol, enclosing
from app.retrieval.direct.search import DirectSearch

MERGE = Symbol("function", "merge", "def merge(self, other):", 4, 6, ())
BASKET = Symbol("class", "Basket", "class Basket:", 3, 6, (MERGE,))


@pytest.mark.usefixtures("grammars")
def test_outline_lists_classes_with_indented_methods(search: DirectSearch) -> None:
    assert search.outline("src/shop/basket.py") == (
        "src/shop/basket.py outline (9 lines)\n"
        "3-6 class class Basket:\n"
        "  4-6 function def merge(self, other):\n"
        "8-9 function def apply_voucher(basket):"
    )


@pytest.mark.usefixtures("grammars")
def test_outline_works_for_typescript(search: DirectSearch) -> None:
    assert "method apply(" in search.outline("src/shop/offer.ts")


@pytest.mark.usefixtures("grammars")
def test_outline_of_a_doc_with_no_symbols_says_use_read_file(search: DirectSearch) -> None:
    with pytest.raises(CannotOutline, match="use read_file instead"):
        search.outline("docs/vouchers.md")


@pytest.mark.usefixtures("grammars")
def test_outline_of_an_unknown_file_type_says_use_read_file(
    repo: Path, search: DirectSearch
) -> None:
    (repo / "notes.xyz").write_text("voucher notes\n")

    with pytest.raises(CannotOutline) as raised:
        search.outline("notes.xyz")

    assert raised.value.path == "notes.xyz"


def test_outline_of_an_unreadable_file_raises_not_text(repo: Path, search: DirectSearch) -> None:
    (repo / "src/shop/basket.py").chmod(0)

    with pytest.raises(NotText):
        search.outline("src/shop/basket.py")


def test_enclosing_returns_the_chain_from_outer_to_inner() -> None:
    assert enclosing((BASKET,), 5) == (BASKET, MERGE)


def test_enclosing_is_empty_outside_every_symbol() -> None:
    assert enclosing((BASKET,), 1) == ()
