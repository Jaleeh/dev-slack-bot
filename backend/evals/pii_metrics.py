"""Scores a redactor's output against the values planted in each snippet."""

from collections import Counter
from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict

from evals.pii_set import NAMED_TYPES, PiiType, PlantedValue, Snippet, name_words


class SnippetResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    caught: tuple[PlantedValue, ...]
    missed: tuple[PlantedValue, ...]
    wrongly_flagged: tuple[str, ...]


class PiiMetrics(BaseModel):
    """A rate is None when there was nothing to count."""

    model_config = ConfigDict(frozen=True)

    catch_rate: float | None
    catch_rate_by_type: dict[PiiType, float]
    wrong_flag_rate: float | None


def is_caught(planted: PlantedValue, redacted: str) -> bool:
    """A leftover name word still identifies someone; a leftover phone fragment doesn't."""
    if planted.value in redacted:
        return False

    if planted.type in NAMED_TYPES:
        return not any(word in redacted for word in name_words(planted.value))

    return True


def score_snippet(snippet: Snippet, redacted: str) -> SnippetResult:
    caught = tuple(planted for planted in snippet.planted if is_caught(planted, redacted))

    return SnippetResult(
        id=snippet.id,
        caught=caught,
        missed=tuple(planted for planted in snippet.planted if planted not in caught),
        wrongly_flagged=tuple(
            lookalike for lookalike in snippet.lookalikes if lookalike not in redacted
        ),
    )


def pii_metrics(snippets: Sequence[Snippet], results: Sequence[SnippetResult]) -> PiiMetrics:
    caught = [planted.type for result in results for planted in result.caught]
    planted = [planted.type for result in results for planted in (*result.caught, *result.missed)]
    caught_by_type = Counter(caught)
    planted_by_type = Counter(planted)

    lookalikes = sum(len(snippet.lookalikes) for snippet in snippets)
    wrongly_flagged = sum(len(result.wrongly_flagged) for result in results)

    return PiiMetrics(
        catch_rate=_rate(len(caught), len(planted)),
        catch_rate_by_type={
            type_: caught_by_type[type_] / count for type_, count in planted_by_type.items()
        },
        wrong_flag_rate=_rate(wrongly_flagged, lookalikes),
    )


def _rate(count: int, total: int) -> float | None:
    return count / total if total else None
