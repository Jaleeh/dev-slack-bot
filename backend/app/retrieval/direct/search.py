"""The search tools the agent calls; each returns plain text for the model."""

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from itertools import chain
from pathlib import Path

import regex
from tree_sitter_language_pack import DownloadError

from app.retrieval.direct.errors import BadLineRange, CannotOutline, NotAFolder, NotText
from app.retrieval.direct.hits import (
    FileHits,
    compile_pattern,
    describe_file,
    describe_rest,
    hit_lines,
    within_cap,
)
from app.retrieval.direct.lines import clip, read_lines
from app.retrieval.direct.outline import Symbol, describe, symbols
from app.retrieval.direct.scope import (
    SearchScope,
    is_text,
    is_visible,
    is_visible_text,
    relative,
    resolve,
    text_files,
)

MAX_READ_LINES = 200

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DirectSearch:
    scope: SearchScope

    def list_files(self, path: str = ".") -> str:
        """The visible entries directly inside a folder, sorted, with folders ending in `/`."""
        folder = resolve(self.scope, path)
        if not folder.is_dir():
            raise NotAFolder(path)

        entries = sorted(entry for entry in folder.iterdir() if is_visible(self.scope, entry))
        return "\n".join(entry.name + "/" if entry.is_dir() else entry.name for entry in entries)

    def read_file(self, path: str, start_line: int = 1, end_line: int | None = None) -> str:
        """Numbered lines `start_line` to `end_line`, at most `MAX_READ_LINES` of them."""
        absolute = resolve(self.scope, path)
        name = relative(self.scope, absolute)
        if absolute.is_dir():
            return f"{name} is a folder. It contains:\n{self.list_files(path)}"
        if not is_text(absolute):
            raise NotText(name)

        lines = read_lines(absolute)
        cap = start_line + MAX_READ_LINES - 1
        end = cap if end_line is None else end_line
        starts_inside_file = 1 <= start_line <= min(end, len(lines))
        if not starts_inside_file:
            raise BadLineRange(name, start_line, end, len(lines))

        last = min(end, cap, len(lines))
        numbered = (f"{n}: {clip(lines[n - 1])}" for n in range(start_line, last + 1))
        return "\n".join([f"{name} lines {start_line}-{last} of {len(lines)}", *numbered])

    def outline(self, path: str) -> str:
        absolute = resolve(self.scope, path)
        name = relative(self.scope, absolute)
        if absolute.is_dir():
            raise CannotOutline(name, "it is a folder")
        if not is_text(absolute):
            raise NotText(name)

        lines = read_lines(absolute)
        header = f"{name} outline ({len(lines)} lines)"
        return "\n".join([header, *describe(symbols(name, "\n".join(lines)))])

    def grep(self, pattern: str, path: str = ".") -> str:
        """Case-insensitive regex hits in the text files under `path`, grouped by file."""
        compiled = compile_pattern(pattern)
        every_file = (self.file_hits(compiled, file) for file in self.searchable(path))
        found = [hits for hits in every_file if hits.hits]
        if not found:
            return "no matches"

        shown = within_cap(found)
        sections = (describe_file(part, self.labels(part.file)) for part in shown)
        return "\n".join(chain(*sections, describe_rest(found, shown)))

    def file_hits(self, pattern: regex.Pattern[str], file: Path) -> FileHits:
        lines = read_lines(file)
        return FileHits(relative(self.scope, file), lines, hit_lines(pattern, lines))

    def searchable(self, path: str) -> Iterable[Path]:
        target = resolve(self.scope, path)
        if target.is_dir():
            return text_files(self.scope, target)
        return (target,) if is_visible_text(self.scope, target) else ()

    def labels(self, hits: FileHits) -> tuple[Symbol, ...]:
        try:
            return symbols(hits.name, "\n".join(hits.lines))
        except CannotOutline as error:
            if isinstance(error.__cause__, DownloadError):
                logger.warning("grep labels skipped for %s: %s", hits.name, error.reason)

            # A file with no parser is still worth grepping; its hits just go unlabelled.
            return ()
