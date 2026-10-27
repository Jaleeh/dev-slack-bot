"""Pins how pathspec applies .gitignore rules for the search scope."""

from pathspec import GitIgnoreSpec


def test_gitignore_spec_honours_negation() -> None:
    spec = GitIgnoreSpec.from_lines(["*.pyc", "!keep.pyc"])

    assert spec.match_file("a.pyc")
    assert not spec.match_file("keep.pyc")


def test_gitignore_spec_matches_a_folder_rule_against_files_inside() -> None:
    assert GitIgnoreSpec.from_lines(["build/"]).match_file("build/x.py")
