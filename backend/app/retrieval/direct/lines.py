"""File text as the numbered lines the search tools show."""

from pathlib import Path

MAX_CHARS = 300
CLIPPED = "…"


def read_lines(file: Path) -> tuple[str, ...]:
    text = file.read_text(encoding="utf-8", errors="replace").removesuffix("\n")

    # Tree-sitter breaks lines only on "\n"; str.splitlines also breaks on form feeds and others.
    return tuple(line.removesuffix("\r") for line in text.split("\n")) if text else ()


def clip(line: str) -> str:
    """`line` cut to `MAX_CHARS`, so one minified line can't fill the model's context."""
    return line if len(line) <= MAX_CHARS else line[:MAX_CHARS] + CLIPPED
