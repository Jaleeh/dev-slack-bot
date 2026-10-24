import pytest

from evals.retrieval_metrics import recall_at_k, reciprocal_rank

A = "src/a.py"
B = "src/b.py"
X = "src/x.py"
Y = "src/y.py"


def test_recall_is_one_when_every_correct_file_is_in_the_top_k() -> None:
    assert recall_at_k([A, B, X], frozenset({A, B}), 5) == 1.0


def test_recall_is_zero_when_no_correct_file_is_found() -> None:
    assert recall_at_k([X, Y], frozenset({A}), 5) == 0.0


def test_recall_counts_only_files_inside_the_top_k() -> None:
    assert recall_at_k([X, A, Y, B], frozenset({A, B}), 2) == 0.5


def test_recall_works_when_there_are_fewer_results_than_k() -> None:
    assert recall_at_k([A], frozenset({A, B}), 5) == 0.5


def test_recall_never_exceeds_one_when_a_file_repeats() -> None:
    assert recall_at_k([A, A, A], frozenset({A, B}), 5) == 0.5


def test_duplicates_do_not_push_later_files_out_of_the_top_k() -> None:
    assert recall_at_k([A, A, B], frozenset({A, B}), 2) == 1.0


def test_recall_is_zero_for_no_results() -> None:
    assert recall_at_k([], frozenset({A}), 5) == 0.0


def test_paths_must_match_exactly() -> None:
    assert recall_at_k(["./src/a.py"], frozenset({"src/a.py"}), 5) == 0.0


def test_reciprocal_rank_is_one_when_a_correct_file_comes_first() -> None:
    assert reciprocal_rank([A, X], frozenset({A})) == 1.0


def test_reciprocal_rank_uses_the_first_correct_file() -> None:
    assert reciprocal_rank([X, Y, B, A], frozenset({A, B})) == pytest.approx(1 / 3)


def test_reciprocal_rank_is_zero_when_no_correct_file_is_found() -> None:
    assert reciprocal_rank([X, Y], frozenset({A})) == 0.0


def test_reciprocal_rank_counts_a_duplicate_once() -> None:
    assert reciprocal_rank([X, X, A], frozenset({A})) == 0.5


def test_recall_rejects_k_below_one() -> None:
    with pytest.raises(ValueError, match="k"):
        recall_at_k([A], frozenset({A}), 0)


def test_recall_rejects_no_correct_files() -> None:
    with pytest.raises(ValueError, match="relevant"):
        recall_at_k([A], frozenset(), 5)


def test_reciprocal_rank_rejects_no_correct_files() -> None:
    with pytest.raises(ValueError, match="relevant"):
        reciprocal_rank([A], frozenset())
