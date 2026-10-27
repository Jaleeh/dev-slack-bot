"""Pins how the regex package times out and fails for the grep search tool."""

import pytest
import regex

# regex shortcuts the textbook "(a+)+$", so this alternation is what still backtracks.
CATASTROPHIC = "(a|aa)+$"
SLOW_LINE = "a" * 40 + "b"


def test_search_past_its_timeout_raises_timeout_error() -> None:
    with pytest.raises(TimeoutError):
        regex.compile(CATASTROPHIC).search(SLOW_LINE, timeout=0.1)


def test_bad_pattern_raises_regex_error() -> None:
    with pytest.raises(regex.error):
        regex.compile("(")


def test_ignorecase_matches_like_re() -> None:
    assert regex.compile("VOUCHER", regex.IGNORECASE).search("a voucher") is not None
