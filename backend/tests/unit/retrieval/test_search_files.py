from pathlib import Path

import pytest

from app.retrieval.direct.errors import (
    BadLineRange,
    NotAFolder,
    NotText,
    PathNotFound,
    PathOutsideRepo,
)
from app.retrieval.direct.scope import open_scope
from app.retrieval.direct.search import DirectSearch


def test_list_files_marks_folders_and_hides_ignored_entries(search: DirectSearch) -> None:
    assert search.list_files(".").splitlines() == [".gitignore", "assets/", "docs/", "src/"]


def test_list_files_hides_symlinks_to_outside_or_ignored_places(search: DirectSearch) -> None:
    assert search.list_files("docs").splitlines() == ["vouchers.md"]


def test_list_files_on_a_file_raises_not_a_folder(search: DirectSearch) -> None:
    with pytest.raises(NotAFolder):
        search.list_files("src/shop/basket.py")


def test_read_file_numbers_the_requested_lines(search: DirectSearch) -> None:
    text = search.read_file("src/shop/long.py", 10, 12)

    assert text == "src/shop/long.py lines 10-12 of 450\n10: line 10\n11: line 11\n12: line 12"


def test_read_file_caps_a_call_at_200_lines(search: DirectSearch) -> None:
    lines = search.read_file("src/shop/long.py", 1, 450).splitlines()

    assert lines[0] == "src/shop/long.py lines 1-200 of 450"
    assert lines[-1] == "200: line 200"


def test_read_file_from_a_start_line_reads_up_to_200_lines(search: DirectSearch) -> None:
    lines = search.read_file("src/shop/long.py", 300).splitlines()

    assert lines[0] == "src/shop/long.py lines 300-450 of 450"


def test_read_file_breaks_lines_only_on_newlines(repo: Path, search: DirectSearch) -> None:
    (repo / "src/feed.py").write_text("def a():\n    pass\n\x0c\ndef b():\n    pass\n")

    assert search.read_file("src/feed.py", 4, 4) == "src/feed.py lines 4-4 of 5\n4: def b():"


def test_read_file_past_the_end_names_the_length(search: DirectSearch) -> None:
    with pytest.raises(BadLineRange) as raised:
        search.read_file("src/shop/long.py", 900, 950)

    assert raised.value.line_count == 450


def test_read_file_says_when_the_end_is_before_the_start(search: DirectSearch) -> None:
    with pytest.raises(BadLineRange) as raised:
        search.read_file("src/shop/long.py", 20, 10)

    assert str(raised.value) == (
        "cannot read lines 20-10 of src/shop/long.py: the end line is before the start line"
    )


def test_read_file_says_when_the_file_is_empty(repo: Path, search: DirectSearch) -> None:
    (repo / "src/empty.py").write_text("")

    with pytest.raises(BadLineRange) as raised:
        search.read_file("src/empty.py")

    assert str(raised.value) == "cannot read lines 1-200 of src/empty.py: the file is empty"


def test_read_file_clips_a_long_line(repo: Path, search: DirectSearch) -> None:
    (repo / "src/blob.xyz").write_text("x" * 1000 + "\n")

    assert search.read_file("src/blob.xyz") == "src/blob.xyz lines 1-1 of 1\n1: " + "x" * 300 + "…"


def test_read_file_refuses_a_binary_file(search: DirectSearch) -> None:
    with pytest.raises(NotText):
        search.read_file("assets/logo.png")


def test_read_file_keeps_git_hidden_even_if_gitignore_unignores_it(repo: Path) -> None:
    (repo / ".gitignore").write_text("build/\n!.git/\n")

    with pytest.raises(PathNotFound):
        DirectSearch(open_scope(repo)).read_file(".git/config")


def test_read_file_on_a_folder_lists_it(search: DirectSearch) -> None:
    text = search.read_file("src/shop")

    assert text == "src/shop is a folder. It contains:\nbasket.py\nlong.py\noffer.ts"


def test_read_file_refuses_parent_traversal(search: DirectSearch) -> None:
    with pytest.raises(PathOutsideRepo):
        search.read_file("src/../../x")


def test_read_file_refuses_an_absolute_path(search: DirectSearch) -> None:
    with pytest.raises(PathOutsideRepo):
        search.read_file("/etc/passwd")


def test_read_file_refuses_a_symlink_outside_the_repo(search: DirectSearch) -> None:
    with pytest.raises(PathOutsideRepo):
        search.read_file("docs/link.txt")


def test_read_file_reports_a_missing_path(search: DirectSearch) -> None:
    with pytest.raises(PathNotFound) as raised:
        search.read_file("src/nope.py")

    assert raised.value.path == "src/nope.py"


def test_read_file_treats_an_ignored_path_as_missing(search: DirectSearch) -> None:
    with pytest.raises(PathNotFound):
        search.read_file("build/out.py")


def test_read_file_treats_a_path_with_a_nul_byte_as_missing(search: DirectSearch) -> None:
    with pytest.raises(PathNotFound):
        search.read_file("src/a\x00b.py")
