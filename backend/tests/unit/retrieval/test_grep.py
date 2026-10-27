from pathlib import Path

import pytest

from app.retrieval.direct.errors import BadPattern
from app.retrieval.direct.scope import open_scope
from app.retrieval.direct.search import DirectSearch


def test_grep_is_case_insensitive_and_searches_docs(search: DirectSearch) -> None:
    assert "docs/vouchers.md (1 hits)" in search.grep("VOUCHER")


@pytest.mark.usefixtures("grammars")
def test_grep_searches_only_visible_text_files(search: DirectSearch) -> None:
    assert search.grep("voucher") == (
        "docs/vouchers.md (1 hits)\n"
        "  1> Vouchers apply after offers.\n"
        "src/shop/basket.py (1 hits)\n"
        "  in apply_voucher\n"
        "  7: \n"
        "  8> def apply_voucher(basket):\n"
        "  9:     return basket\n"
        "src/shop/offer.ts (1 hits)\n"
        "  1> // Offers can stack with a voucher.\n"
        "  2: export class Offer {"
    )


@pytest.mark.usefixtures("grammars")
def test_grep_labels_a_hit_with_its_enclosing_symbols(search: DirectSearch) -> None:
    assert "  in Basket > merge\n" in search.grep("merge_lines")


def test_grep_shows_one_line_of_context(search: DirectSearch) -> None:
    output = search.grep("^line 100$", "src/shop/long.py")

    assert output == "src/shop/long.py (1 hits)\n  99: line 99\n  100> line 100\n  101: line 101"


def test_grep_caps_hits_and_says_how_many_more(search: DirectSearch) -> None:
    output = search.grep("line", "src/shop/long.py")

    assert output.endswith("  40> line 40\n  41: line 41\n... 410 more hits in 0 more files")


def test_grep_counts_files_left_out_by_the_cap(search: DirectSearch) -> None:
    output = search.grep("line|voucher", "src/shop")

    assert output.endswith("... 414 more hits in 1 more files")


def test_grep_reports_no_matches(search: DirectSearch) -> None:
    assert search.grep("zzzz") == "no matches"


def test_grep_with_a_bad_pattern_raises_bad_pattern(search: DirectSearch) -> None:
    with pytest.raises(BadPattern) as raised:
        search.grep("(")

    assert raised.value.pattern == "("


def test_grep_within_a_file_path_searches_only_that_file(search: DirectSearch) -> None:
    assert search.grep("voucher", "src/shop/offer.ts") == (
        "src/shop/offer.ts (1 hits)\n"
        "  1> // Offers can stack with a voucher.\n"
        "  2: export class Offer {"
    )


def test_grep_with_a_too_deeply_nested_pattern_raises_bad_pattern(search: DirectSearch) -> None:
    with pytest.raises(BadPattern):
        search.grep("(" * 2000 + "a" + ")" * 2000)


def test_grep_on_a_file_with_no_parser_shows_hits_without_labels(
    repo: Path, search: DirectSearch
) -> None:
    (repo / "notes.xyz").write_text("voucher notes\n")

    assert search.grep("voucher", "notes.xyz") == "notes.xyz (1 hits)\n  1> voucher notes"


def test_grep_skips_noise_in_a_repo_without_a_gitignore(tmp_path: Path) -> None:
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules/a.js").write_text("voucher\n")
    (tmp_path / "a.txt").write_text("voucher\n")

    assert DirectSearch(open_scope(tmp_path)).grep("voucher") == "a.txt (1 hits)\n  1> voucher"


def test_grep_clips_a_long_line(repo: Path, search: DirectSearch) -> None:
    (repo / "src/blob.xyz").write_text("voucher" + "x" * 1000 + "\n")

    assert search.grep("voucher", "src/blob.xyz") == (
        "src/blob.xyz (1 hits)\n  1> voucher" + "x" * 293 + "…"
    )


def test_grep_skips_a_file_it_cannot_read(repo: Path, search: DirectSearch) -> None:
    (repo / "notes").mkdir()
    (repo / "notes/open.xyz").write_text("voucher\n")
    (repo / "notes/locked.xyz").write_text("voucher\n")
    (repo / "notes/locked.xyz").chmod(0)

    assert search.grep("voucher", "notes") == "notes/open.xyz (1 hits)\n  1> voucher"


def test_grep_refuses_a_pattern_too_slow_to_run(repo: Path, search: DirectSearch) -> None:
    (repo / "src/slow.txt").write_text("a" * 40 + "b\n")

    with pytest.raises(BadPattern, match="too slow"):
        search.grep("(a|aa)+$", "src/slow.txt")


def test_grep_skips_translation_files(repo: Path, search: DirectSearch) -> None:
    po = repo / "src/shop/locale/de/LC_MESSAGES/django.po"
    po.parent.mkdir(parents=True)
    po.write_text('msgid "voucher"\n')

    assert search.grep("voucher", "src/shop/locale") == "no matches"
