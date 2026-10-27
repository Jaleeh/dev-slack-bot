"""Which paths in a repository the search tools may see."""

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

from pathspec import GitIgnoreSpec

from app.retrieval.direct.errors import PathNotFound, PathOutsideRepo

DEFAULT_SKIP = (
    "**/migrations/",
    "node_modules/",
    "vendor/",
    "*.lock",
    "package-lock.json",
    "*.min.js",
    "*.min.css",
    "**/locale/**/*.po",
)
ALWAYS_SKIP = ".git/"
BINARY_SNIFF_BYTES = 8192


@dataclass(frozen=True)
class SearchScope:
    root: Path
    ignore: GitIgnoreSpec


def open_scope(root: Path, skip: Sequence[str] = DEFAULT_SKIP) -> SearchScope:
    resolved = root.resolve()
    gitignore = resolved / ".gitignore"
    rules = gitignore.read_text(encoding="utf-8").splitlines() if gitignore.is_file() else []

    # The last matching rule wins, so a repo's "!.git/" can't make .git visible again.
    return SearchScope(resolved, GitIgnoreSpec.from_lines([*skip, *rules, ALWAYS_SKIP]))


def resolve(scope: SearchScope, path: str) -> Path:
    """The existing, visible path inside the root that `path` names."""
    try:
        absolute = (scope.root / path).resolve()
        exists = absolute.exists()
    except (ValueError, OSError) as error:
        raise PathNotFound(path) from error

    if not absolute.is_relative_to(scope.root):
        raise PathOutsideRepo(path)
    if not exists or is_ignored(scope, absolute):
        raise PathNotFound(path)

    return absolute


def relative(scope: SearchScope, absolute: Path) -> str:
    return absolute.relative_to(scope.root).as_posix()


def text_files(scope: SearchScope, folder: Path) -> Iterator[Path]:
    """Visible text files under `folder`, in sorted walk order, never entering ignored folders."""
    for parent, folders, files in folder.walk():
        # Path.walk only skips a folder when this list is changed in place.
        folders[:] = sorted(name for name in folders if not is_ignored(scope, parent / name))
        yield from (
            parent / name for name in sorted(files) if is_visible_text(scope, parent / name)
        )


def is_ignored(scope: SearchScope, absolute: Path) -> bool:
    if absolute == scope.root:
        return False

    name = relative(scope, absolute)
    return scope.ignore.match_file(f"{name}/" if absolute.is_dir() else name)


def is_visible(scope: SearchScope, path: Path) -> bool:
    """Whether `path` and, for a symlink, its target are inside the root and not ignored."""
    target = path.resolve()
    if not target.is_relative_to(scope.root):
        return False

    return not (is_ignored(scope, path) or is_ignored(scope, target))


def is_visible_text(scope: SearchScope, file: Path) -> bool:
    return is_visible(scope, file) and file.is_file() and is_text(file)


def is_text(file: Path) -> bool:
    """Whether `file` can be read and has no NUL byte near its start."""
    try:
        with file.open("rb") as stream:
            return b"\x00" not in stream.read(BINARY_SNIFF_BYTES)
    except OSError:
        # An unreadable or vanished file is left out rather than failing the whole search.
        return False
