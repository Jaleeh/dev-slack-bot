"""Pure decisions for the search loop: which tool calls run, and when the loop stops."""

import json
import posixpath
from collections.abc import Mapping
from dataclasses import dataclass, replace
from enum import Enum

from app.retrieval.direct.search import MAX_READ_LINES

CODE_TOOLS = frozenset({"grep", "read_file", "outline"})
MAX_REPEATS = 2


class Check(Enum):
    RUN = "run"
    REPEAT = "repeat"
    REREAD = "reread"


class Outcome(Enum):
    RAN = "ran"
    # read_file on a folder returns its listing, which reads no code.
    LISTED = "listed"
    FAILED = "failed"
    REPEAT = "repeat"
    REREAD = "reread"


class StopReason(Enum):
    ANSWERED = "answered"
    TOOL_LIMIT = "tool limit"
    TOKEN_LIMIT = "token limit"
    REPEATS = "repeated calls"


class Route(Enum):
    TOOLS = "tools"
    NUDGE = "nudge"
    FINISH = "finish"


@dataclass(frozen=True)
class Call:
    name: str
    args: Mapping[str, object]

    @property
    def path(self) -> str:
        return posixpath.normpath(str(self.args.get("path", "")))

    @property
    def key(self) -> str:
        return self.name + json.dumps(self.args, sort_keys=True, default=str)


@dataclass(frozen=True)
class Limits:
    max_tool_calls: int
    max_tokens: int


@dataclass(frozen=True)
class Progress:
    tool_calls: int = 0
    tokens: int = 0
    repeats: int = 0
    searched: bool = False
    nudged: bool = False
    stop: StopReason | None = None
    seen: frozenset[str] = frozenset()
    read_lines: frozenset[tuple[str, int]] = frozenset()


def check(progress: Progress, call: Call) -> Check:
    if call.key in progress.seen:
        return Check.REPEAT

    lines = covered_lines(call)
    if lines and lines <= progress.read_lines:
        return Check.REREAD

    return Check.RUN


def after_call(progress: Progress, call: Call, outcome: Outcome) -> Progress:
    ran = outcome is Outcome.RAN

    return replace(
        progress,
        tool_calls=progress.tool_calls + 1,
        repeats=progress.repeats + (outcome is Outcome.REPEAT),
        searched=progress.searched or (ran and call.name in CODE_TOOLS),
        seen=progress.seen | {call.key},
        read_lines=(progress.read_lines | covered_lines(call)) if ran else progress.read_lines,
    )


def add_tokens(progress: Progress, tokens: int) -> Progress:
    return replace(progress, tokens=progress.tokens + tokens)


def stop_reason(progress: Progress, limits: Limits) -> StopReason | None:
    if progress.repeats >= MAX_REPEATS:
        return StopReason.REPEATS
    if progress.tool_calls >= limits.max_tool_calls:
        return StopReason.TOOL_LIMIT
    if progress.tokens >= limits.max_tokens:
        return StopReason.TOKEN_LIMIT

    return None


def after_reply(progress: Progress, has_tool_calls: bool) -> Route:
    """Where the loop goes after a model reply. A forced reply always finishes."""
    if progress.stop is not None:
        return Route.FINISH
    if has_tool_calls:
        return Route.TOOLS
    if progress.searched or progress.nudged:
        return Route.FINISH

    return Route.NUDGE


def covered_lines(call: Call) -> frozenset[tuple[str, int]]:
    """The (path, line) pairs a `read_file` call asks for, capped as the tool caps them."""
    if call.name != "read_file":
        return frozenset()

    try:
        start = _as_int(call.args.get("start_line", 1))
        cap = start + MAX_READ_LINES - 1
        end = call.args.get("end_line")
        last = cap if end is None else min(_as_int(end), cap)
    except ValueError:
        # The tool refuses such a call itself, so it covers nothing.
        return frozenset()

    return frozenset((call.path, line) for line in range(start, last + 1))


def _as_int(value: object) -> int:
    return value if isinstance(value, int) else int(str(value))
