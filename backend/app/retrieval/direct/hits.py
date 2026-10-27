"""Grep hits in a file, the cap on how many are shown, and how they are written out."""

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from itertools import accumulate, groupby

import regex

from app.retrieval.direct.errors import BadPattern
from app.retrieval.direct.lines import clip
from app.retrieval.direct.outline import Symbol, enclosing

MAX_SHOWN = 40
CONTEXT_LINES = 1
# Per line, so one runaway pattern stops the whole grep almost at once.
MATCH_TIMEOUT_SECONDS = 0.1


@dataclass(frozen=True)
class FileHits:
    name: str
    lines: tuple[str, ...]
    hits: tuple[int, ...]


@dataclass(frozen=True)
class ShownHits:
    """The hits of one file that fit under the cap."""

    file: FileHits
    hits: tuple[int, ...]


def compile_pattern(pattern: str) -> regex.Pattern[str]:
    try:
        return regex.compile(pattern, regex.IGNORECASE)
    except (regex.error, RecursionError) as error:
        raise BadPattern(pattern, str(error)) from error


def hit_lines(pattern: regex.Pattern[str], lines: Sequence[str]) -> tuple[int, ...]:
    try:
        return tuple(
            n
            for n, line in enumerate(lines, 1)
            if pattern.search(line, timeout=MATCH_TIMEOUT_SECONDS)
        )
    except TimeoutError as error:
        raise BadPattern(pattern.pattern, "too slow; use a simpler pattern") from error


def within_cap(found: Sequence[FileHits]) -> tuple[ShownHits, ...]:
    """The leading files' hits, cut so at most `MAX_SHOWN` are shown in total."""
    hits_before = accumulate((len(file.hits) for file in found), initial=0)

    return tuple(
        ShownHits(file, file.hits[: MAX_SHOWN - before])
        for file, before in zip(found, hits_before, strict=False)
        if before < MAX_SHOWN
    )


def describe_file(shown: ShownHits, symbols: Sequence[Symbol]) -> Iterator[str]:
    """A header with the file's full hit count, then each shown hit in its context."""
    file = shown.file
    yield f"{file.name} ({len(file.hits)} hits)"

    for block in context_blocks(shown):
        first_hit = next(n for n in block if n in shown.hits)
        chain = enclosing(symbols, first_hit)
        if chain:
            yield "  in " + " > ".join(symbol.name for symbol in chain)

        yield from (
            f"  {n}{'>' if n in shown.hits else ':'} {clip(file.lines[n - 1])}" for n in block
        )


def describe_rest(found: Sequence[FileHits], shown: Sequence[ShownHits]) -> Iterator[str]:
    more_hits = sum(len(file.hits) for file in found) - sum(len(part.hits) for part in shown)

    if more_hits:
        yield f"... {more_hits} more hits in {len(found) - len(shown)} more files"


def context_blocks(shown: ShownHits) -> list[list[int]]:
    """The shown hit lines plus their context, merged into runs of consecutive line numbers."""
    line_count = len(shown.file.lines)
    numbers = sorted(
        {
            n
            for hit in shown.hits
            for n in range(hit - CONTEXT_LINES, hit + CONTEXT_LINES + 1)
            if 1 <= n <= line_count
        }
    )

    return [
        [n for _, n in run]
        for _, run in groupby(enumerate(numbers), lambda pair: pair[1] - pair[0])
    ]
