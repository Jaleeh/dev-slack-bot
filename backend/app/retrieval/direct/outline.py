"""Classes and functions in a source file, found with tree-sitter."""

from collections.abc import Iterator, Sequence
from dataclasses import dataclass

from tree_sitter_language_pack import (
    Error,
    ProcessConfig,
    StructureItem,
    detect_language_from_path,
    process,
)

from app.retrieval.direct.errors import CannotOutline

INDENT = "  "


@dataclass(frozen=True)
class Symbol:
    """A class, function or similar; lines are 1-based and inclusive."""

    kind: str
    name: str
    signature: str
    start_line: int
    end_line: int
    children: tuple[Symbol, ...]


def symbols(path: str, source: str) -> tuple[Symbol, ...]:
    """The top-level symbols in `source`; `path` picks the language by its extension."""
    language = detect_language_from_path(path)
    if language is None:
        raise CannotOutline(path, "its file type has no parser")

    try:
        items = process(source, ProcessConfig(language=language, structure=True)).structure
    except Error as error:
        raise CannotOutline(path, str(error)) from error

    found = to_symbols(items)
    if not found:
        raise CannotOutline(path, "no classes or functions found")

    return found


def enclosing(symbols: Sequence[Symbol], line: int) -> tuple[Symbol, ...]:
    """The symbols containing `line`, outermost first."""
    for symbol in symbols:
        if symbol.start_line <= line <= symbol.end_line:
            return (symbol, *enclosing(symbol.children, line))
    return ()


def describe(symbols: Sequence[Symbol], depth: int = 0) -> Iterator[str]:
    """One line per symbol, children indented under their parent."""
    for symbol in symbols:
        signature = symbol.signature.partition("\n")[0]
        yield f"{INDENT * depth}{symbol.start_line}-{symbol.end_line} {symbol.kind} {signature}"
        yield from describe(symbol.children, depth + 1)


def to_symbols(items: Sequence[StructureItem]) -> tuple[Symbol, ...]:
    return tuple(
        Symbol(
            kind=str(item.kind).lower(),
            name=item.name or "",
            signature=item.signature or item.name or "",
            start_line=item.span.start_line + 1,
            end_line=item.span.end_line + 1,
            children=to_symbols(item.children),
        )
        for item in items
        if item.span is not None
    )
