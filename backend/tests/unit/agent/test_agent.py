from pathlib import Path

import pytest

from app.agent.graph import Agent, AgentResult, repo_map
from app.agent.guardrails import Limits, Outcome, StopReason
from app.agent.prompts import ANSWER_NOW, FALLBACK, SEARCH_FIRST
from app.retrieval.direct.scope import open_scope
from app.retrieval.direct.search import DirectSearch
from tests.scripted_model import ROOMY, ScriptedModel, calls, scripted


@pytest.fixture
def search(tmp_path: Path) -> DirectSearch:
    files = {
        "src/voucher.py": "def apply_voucher():\n    return 'voucher'\n",
        "src/basket.py": "class Basket:\n    pass\n",
        "README.md": "Vouchers apply at checkout.\n",
        "node_modules/lib.js": "const voucher = 1\n",
    }
    for name, text in files.items():
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text(text)

    return DirectSearch(open_scope(tmp_path))


def grep(pattern: str = "voucher") -> tuple[str, dict[str, object]]:
    return ("grep", {"pattern": pattern})


def ask(
    search: DirectSearch,
    search_model: ScriptedModel,
    rewrite_model: ScriptedModel,
    limits: Limits = ROOMY,
) -> AgentResult:
    return Agent(search_model, rewrite_model, search, limits).ask("Why is the voucher rejected?")


def test_answers_after_searching_and_rewrites_the_draft(search: DirectSearch) -> None:
    result = ask(search, scripted(calls(grep()), "draft"), scripted("plain answer"))

    assert result.answer == "plain answer"
    assert result.draft == "draft"
    assert result.stop is StopReason.ANSWERED
    assert result.tool_calls[0].name == "grep"


def test_an_answer_without_searching_is_sent_back_once(search: DirectSearch) -> None:
    search_model = scripted("guess", calls(grep()), "draft")

    result = ask(search, search_model, scripted("plain"))

    assert search_model.inputs[1][-1].content == SEARCH_FIRST
    assert result.answer == "plain"


def test_a_second_blocked_repeat_forces_the_answer(search: DirectSearch) -> None:
    search_model = scripted(calls(grep()), calls(grep()), calls(grep()), "draft")

    result = ask(search, search_model, scripted("plain"))

    assert result.stop is StopReason.REPEATS
    assert [call.outcome for call in result.tool_calls] == [
        Outcome.RAN,
        Outcome.REPEAT,
        Outcome.REPEAT,
    ]


def test_tool_limit_forces_an_answer_with_tools_still_bound(search: DirectSearch) -> None:
    search_model = scripted(calls(grep("voucher"), grep("basket")), "draft")

    result = ask(
        search, search_model, scripted("plain"), Limits(max_tool_calls=2, max_tokens=10**6)
    )

    assert result.stop is StopReason.TOOL_LIMIT
    assert search_model.inputs[-1][-1].content == ANSWER_NOW
    assert search_model.tools_per_call[-1] == ("list_files", "grep", "read_file", "outline")


def test_token_limit_forces_an_answer(search: DirectSearch) -> None:
    search_model = scripted(calls(grep(), tokens=110), "draft")

    result = ask(search, search_model, scripted("plain"), Limits(max_tool_calls=15, max_tokens=100))

    assert result.stop is StopReason.TOKEN_LIMIT


def test_a_forced_reply_that_only_calls_a_tool_gives_the_fallback(search: DirectSearch) -> None:
    search_model = scripted(calls(grep()), calls(("read_file", {"path": "src/voucher.py"})))

    result = ask(search, search_model, scripted(), Limits(max_tool_calls=1, max_tokens=10**6))

    assert result.answer == FALLBACK
    assert result.is_empty
    assert [call.name for call in result.tool_calls] == ["grep"]


def test_a_search_error_goes_back_to_the_model_as_text(search: DirectSearch) -> None:
    search_model = scripted(calls(("read_file", {"path": "../x"}), grep()), "draft")

    result = ask(search, search_model, scripted("plain"))

    assert result.tool_calls[0].outcome is Outcome.FAILED
    assert "outside the repository" in result.tool_calls[0].output


def test_string_line_numbers_are_accepted(search: DirectSearch) -> None:
    read: tuple[str, dict[str, object]] = (
        "read_file",
        {"path": "src/voucher.py", "start_line": "1", "end_line": "2"},
    )

    result = ask(search, scripted(calls(read), "draft"), scripted("plain"))

    assert result.tool_calls[0].outcome is Outcome.RAN


def test_a_missing_argument_goes_back_to_the_model_as_text(search: DirectSearch) -> None:
    result = ask(search, scripted(calls(("read_file", {}), grep()), "draft"), scripted("plain"))

    assert result.tool_calls[0].outcome is Outcome.FAILED
    assert "path" in result.tool_calls[0].output


def test_an_empty_rewrite_keeps_the_draft(search: DirectSearch) -> None:
    result = ask(search, scripted(calls(grep()), "draft"), scripted(""))

    assert result.answer == "draft"
    assert not result.is_empty


@pytest.mark.usefixtures("grammars")
def test_files_are_listed_in_first_touched_order(search: DirectSearch) -> None:
    search_model = scripted(
        calls(
            ("outline", {"path": "src/basket.py"}),
            ("read_file", {"path": "./src/voucher.py"}),
            ("read_file", {"path": "src/basket.py"}),
        ),
        "draft",
    )

    result = ask(search, search_model, scripted("plain"))

    assert result.files == ("src/basket.py", "src/voucher.py")


def test_files_read_by_absolute_or_parent_path_are_listed_repo_relative(
    search: DirectSearch, tmp_path: Path
) -> None:
    search_model = scripted(
        calls(
            ("read_file", {"path": f"{tmp_path}/src/voucher.py"}),
            ("read_file", {"path": f"../{tmp_path.name}/src/basket.py"}),
            ("read_file", {"path": "src/voucher.py"}),
        ),
        "draft",
    )

    result = ask(search, search_model, scripted("plain"))

    assert result.files == ("src/voucher.py", "src/basket.py")


def test_repo_map_lists_two_levels_and_skips_noise(search: DirectSearch) -> None:
    assert repo_map(search) == "README.md\nsrc/\n  basket.py\n  voucher.py"


def test_reading_a_folder_does_not_count_as_searching(search: DirectSearch) -> None:
    search_model = scripted(calls(("read_file", {"path": "src"})), "guess", calls(grep()), "draft")

    ask(search, search_model, scripted("plain"))

    assert search_model.inputs[2][-1].content == SEARCH_FIRST


def test_a_folder_read_is_not_listed_as_a_file(search: DirectSearch) -> None:
    search_model = scripted(calls(("read_file", {"path": "src"}), grep()), "draft")

    result = ask(search, search_model, scripted("plain"))

    assert result.files == ()
