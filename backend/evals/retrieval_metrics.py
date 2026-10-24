"""Per-question retrieval scores: ranked file paths against the correct files."""

from collections.abc import Set


def recall_at_k(ranked: list[str], relevant: Set[str], k: int) -> float:
    if k < 1:
        raise ValueError(f"k must be at least 1, got {k}")
    _require_relevant(relevant)

    top_k = _unique(ranked)[:k]

    return sum(path in relevant for path in top_k) / len(relevant)


def reciprocal_rank(ranked: list[str], relevant: Set[str]) -> float:
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
