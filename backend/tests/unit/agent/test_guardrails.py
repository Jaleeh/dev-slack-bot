from app.agent.guardrails import (
    Call,
    Check,
    Limits,
    Outcome,
    Progress,
    Route,
    StopReason,
    add_tokens,
    after_call,
    after_reply,
    check,
    stop_reason,
)

LIMITS = Limits(max_tool_calls=15, max_tokens=1000)


def grep(pattern: str = "x") -> Call:
    return Call("grep", {"pattern": pattern})


def read(start_line: int, end_line: int) -> Call:
    return Call("read_file", {"path": "a.py", "start_line": start_line, "end_line": end_line})


def ran(*calls: Call) -> Progress:
    progress = Progress()
    for call in calls:
        progress = after_call(progress, call, Outcome.RAN)
    return progress


def test_a_new_call_runs() -> None:
    assert check(Progress(), grep()) is Check.RUN


def test_an_identical_call_is_a_repeat() -> None:
    assert check(ran(grep()), grep()) is Check.REPEAT


def test_argument_order_does_not_hide_a_repeat() -> None:
    progress = ran(Call("grep", {"pattern": "x", "path": "src"}))

    assert check(progress, Call("grep", {"path": "src", "pattern": "x"})) is Check.REPEAT


def test_rereading_covered_lines_is_blocked() -> None:
    assert check(ran(read(1, 200)), read(50, 60)) is Check.REREAD


def test_reading_partly_new_lines_runs() -> None:
    assert check(ran(read(1, 200)), read(150, 250)) is Check.RUN


def test_a_failed_read_does_not_cover_lines() -> None:
    progress = after_call(Progress(), read(1, 10), Outcome.FAILED)

    assert check(progress, read(2, 10)) is Check.RUN


def test_list_files_alone_does_not_count_as_searching() -> None:
    progress = ran(Call("list_files", {"path": "."}))

    assert after_reply(progress, False) is Route.NUDGE


def test_a_reply_without_calls_after_a_search_finishes() -> None:
    assert after_reply(ran(grep()), False) is Route.FINISH


def test_the_search_first_nudge_happens_once() -> None:
    assert after_reply(Progress(nudged=True), False) is Route.FINISH


def test_a_reply_with_calls_goes_to_tools() -> None:
    assert after_reply(Progress(), True) is Route.TOOLS


def test_a_forced_reply_always_finishes() -> None:
    assert after_reply(Progress(stop=StopReason.TOOL_LIMIT), True) is Route.FINISH


def test_second_blocked_repeat_stops_the_loop() -> None:
    once = after_call(ran(grep()), grep(), Outcome.REPEAT)
    twice = after_call(once, grep(), Outcome.REPEAT)

    assert stop_reason(once, LIMITS) is None
    assert stop_reason(twice, LIMITS) is StopReason.REPEATS


def test_tool_limit_stops_at_the_limit() -> None:
    fourteen = ran(*(grep(str(n)) for n in range(14)))
    fifteen = after_call(fourteen, grep("last"), Outcome.RAN)

    assert stop_reason(fourteen, LIMITS) is None
    assert stop_reason(fifteen, LIMITS) is StopReason.TOOL_LIMIT


def test_token_limit_stops_at_the_limit() -> None:
    assert stop_reason(add_tokens(Progress(), 1000), LIMITS) is StopReason.TOKEN_LIMIT
