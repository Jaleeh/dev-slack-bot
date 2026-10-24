"""Per-question retrieval scores: ranked file paths against the correct files."""

from collections.abc import Set


def recall_at_k(ranked: list[str], relevant: Set[str], k: int) -> float:
    """Share of the correct files found in the top k results.

    Example: 2 correct files, 1 of them in the top 5, gives recall@5 = 0.5.
    """
    if k < 1:
        raise ValueError(f"k must be at least 1, got {k}")
    _require_relevant(relevant)

    top_k = _unique(ranked)[:k]

    return sum(path in relevant for path in top_k) / len(relevant)


def reciprocal_rank(ranked: list[str], relevant: Set[str]) -> float:
    """1 / the position of the first correct file, or 0.0 if none is found.

    Example: first correct file at position 3 gives 1/3. Averaged over questions, this is MRR.
    """
    _require_relevant(relevant)

    for rank, path in enumerate(_unique(ranked), start=1):
        if path in relevant:
            return 1 / rank

    return 0.0


def _unique(ranked: list[str]) -> list[str]:
    return list(dict.fromkeys(ranked))


def _require_relevant(relevant: Set[str]) -> None:
    if not relevant:
        raise ValueError("relevant must hold at least one file")
