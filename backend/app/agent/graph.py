"""The search agent: a LangGraph loop over the search tools, then a plain-English rewrite."""

import operator
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from itertools import chain
from pathlib import Path
from typing import Annotated, Any, TypedDict

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import StructuredTool
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from pydantic import ValidationError

from app.agent.guardrails import (
    Call,
    Check,
    Limits,
    Outcome,
    Progress,
    StopReason,
    add_tokens,
    after_call,
    after_reply,
    check,
    stop_reason,
)
from app.agent.prompts import (
    ANSWER_NOW,
    FALLBACK,
    REPEAT_BLOCKED,
    REREAD_BLOCKED,
    SEARCH_FIRST,
    rewrite_prompt,
    system_prompt,
)
from app.agent.tools import search_tools
from app.config.agent import AgentSettings, build_rewrite_model, build_search_model
from app.retrieval.direct.errors import SearchError
from app.retrieval.direct.scope import open_scope
from app.retrieval.direct.search import DirectSearch

# Each tool call takes a search step and a tools step, plus the nudge, finish and rewrite.
STEPS_PER_TOOL_CALL = 4
RECURSION_MARGIN = 10
FILE_TOOLS = frozenset({"read_file", "outline"})


@dataclass(frozen=True)
class ToolCallRecord:
    name: str
    args: Mapping[str, object]
    output: str
    outcome: Outcome

    @property
    def signature(self) -> str:
        """The call as the model made it, such as `grep(pattern='voucher')`."""
        args = ", ".join(f"{name}={value!r}" for name, value in self.args.items())

        return f"{self.name}({args})"


@dataclass(frozen=True)
class ModelCall:
    prompt_tokens: int
    output_tokens: int
    done_reason: str

    @property
    def tokens(self) -> int:
        return self.prompt_tokens + self.output_tokens


@dataclass(frozen=True)
class AgentResult:
    answer: str
    draft: str
    stop: StopReason
    tool_calls: tuple[ToolCallRecord, ...]
    files: tuple[str, ...]
    model_calls: tuple[ModelCall, ...]
    tokens: int
    seconds: float

    @property
    def is_empty(self) -> bool:
        """The asker got the fallback because the model gave no answer text."""
        return not self.draft


class AgentState(TypedDict):
    question: str
    messages: Annotated[list[AnyMessage], add_messages]
    records: Annotated[list[ToolCallRecord], operator.add]
    model_calls: Annotated[list[ModelCall], operator.add]
    progress: Progress
    draft: str
    answer: str


def ignore(record: ToolCallRecord) -> None:
    return None


@dataclass(frozen=True)
class Agent:
    search_model: BaseChatModel
    rewrite_model: BaseChatModel
    search: DirectSearch
    limits: Limits

    def ask(self, question: str, on_call: Callable[[ToolCallRecord], None] = ignore) -> AgentResult:
        """Answers one question; `on_call` sees each tool call as it finishes."""
        started = time.monotonic()
        graph = Loop(self, on_call).compile()
        config = {
            "recursion_limit": STEPS_PER_TOOL_CALL * self.limits.max_tool_calls + RECURSION_MARGIN
        }

        state = graph.invoke(initial_state(question, repo_map(self.search)), config)
        result = to_result(state, time.monotonic() - started)

        # The tools accept absolute and `../` paths, so one file can be named several ways.
        repo_files = (self.search.repo_path(path) for path in result.files)
        return replace(result, files=tuple(dict.fromkeys(repo_files)))


def build_agent(settings: AgentSettings, root: Path) -> Agent:
    """The agent the settings describe, searching the repository at `root`."""
    return Agent(
        search_model=build_search_model(settings),
        rewrite_model=build_rewrite_model(settings),
        search=DirectSearch(open_scope(root, settings.search_skip)),
        limits=Limits(settings.agent_max_tool_calls, settings.agent_max_tokens),
    )


@dataclass(frozen=True)
class Toolbox:
    """Runs the search tools by name and records each call the way the agent sees it."""

    search: DirectSearch
    tools: Mapping[str, StructuredTool]

    @classmethod
    def over(cls, search: DirectSearch) -> Toolbox:
        return cls(search, {tool.name: tool for tool in search_tools(search)})

    def execute(self, call: Call) -> ToolCallRecord:
        tool = self.tools.get(call.name)
        if tool is None:
            known = ", ".join(self.tools)
            return record_of(call, f"no tool named {call.name}; use one of {known}", Outcome.FAILED)

        # Bad arguments are the model's mistake, so it gets the reason; anything else is a bug.
        try:
            output = tool.invoke(dict(call.args))
        except (SearchError, ValidationError) as error:
            return record_of(call, str(error), Outcome.FAILED)

        return record_of(call, str(output), self.outcome_of_success(call))

    def outcome_of_success(self, call: Call) -> Outcome:
        is_folder_read = call.name == "read_file" and self.search.is_folder(str(call.args["path"]))

        return Outcome.LISTED if is_folder_read else Outcome.RAN


class Loop:
    """The graph's nodes. Decisions come from the guardrails; this class only does the I/O."""

    def __init__(self, agent: Agent, on_call: Callable[[ToolCallRecord], None]) -> None:
        self.toolbox = Toolbox.over(agent.search)
        # Bound on every call, the forced one too: without tool definitions the model
        # still wrote a tool call and left the answer empty.
        self.searcher = agent.search_model.bind_tools(list(self.toolbox.tools.values()))
        self.rewriter = agent.rewrite_model
        self.limits = agent.limits
        self.on_call = on_call

    def compile(self) -> Any:
        graph = StateGraph(AgentState)
        graph.add_node("search", self.search_step)
        graph.add_node("tools", self.tools_step)
        graph.add_node("nudge", self.nudge_step)
        graph.add_node("finish", self.finish_step)
        graph.add_node("rewrite", self.rewrite_step)

        graph.add_edge(START, "search")
        graph.add_conditional_edges("search", self.route_reply)
        graph.add_edge("tools", "search")
        graph.add_edge("nudge", "search")
        graph.add_conditional_edges("finish", self.route_finish)
        graph.add_edge("rewrite", END)

        return graph.compile()

    def search_step(self, state: AgentState) -> dict[str, object]:
        reply = self.searcher.invoke(state["messages"])
        call = model_call(reply)

        return {
            "messages": [reply],
            "model_calls": [call],
            "progress": add_tokens(state["progress"], call.tokens),
        }

    def route_reply(self, state: AgentState) -> str:
        return after_reply(state["progress"], bool(last_reply(state).tool_calls)).value

    def tools_step(self, state: AgentState) -> dict[str, object]:
        progress = state["progress"]
        records: list[ToolCallRecord] = []
        messages: list[AnyMessage] = []

        for tool_call in last_reply(state).tool_calls:
            call = Call(tool_call["name"], tool_call["args"])
            record = self.run(progress, call)
            progress = after_call(progress, call, record.outcome)
            self.on_call(record)
            records.append(record)
            messages.append(ToolMessage(record.output, tool_call_id=tool_call["id"]))

        stop = stop_reason(progress, self.limits)
        if stop is not None:
            progress = replace(progress, stop=stop)
            messages.append(HumanMessage(ANSWER_NOW))

        return {"messages": messages, "records": records, "progress": progress}

    def run(self, progress: Progress, call: Call) -> ToolCallRecord:
        match check(progress, call):
            case Check.REPEAT:
                return record_of(call, REPEAT_BLOCKED, Outcome.REPEAT)
            case Check.REREAD:
                return record_of(call, REREAD_BLOCKED, Outcome.REREAD)
            case Check.RUN:
                return self.toolbox.execute(call)

    def nudge_step(self, state: AgentState) -> dict[str, object]:
        return {
            "messages": [HumanMessage(SEARCH_FIRST)],
            "progress": replace(state["progress"], nudged=True),
        }

    def finish_step(self, state: AgentState) -> dict[str, object]:
        draft = last_reply(state).text.strip()

        return {"draft": draft} if draft else {"draft": "", "answer": FALLBACK}

    def route_finish(self, state: AgentState) -> str:
        return "rewrite" if state["draft"] else END

    def rewrite_step(self, state: AgentState) -> dict[str, object]:
        reply = self.rewriter.invoke(rewrite_prompt(state["question"], state["draft"]))
        call = model_call(reply)

        return {
            "answer": reply.text.strip() or state["draft"],
            "model_calls": [call],
            "progress": add_tokens(state["progress"], call.tokens),
        }


def initial_state(question: str, repo_map: str) -> AgentState:
    return {
        "question": question,
        "messages": [SystemMessage(system_prompt(repo_map)), HumanMessage(question)],
        "records": [],
        "model_calls": [],
        "progress": Progress(),
        "draft": "",
        "answer": "",
    }


def to_result(state: AgentState, seconds: float) -> AgentResult:
    progress = state["progress"]
    records = tuple(state["records"])

    return AgentResult(
        answer=state["answer"],
        draft=state["draft"],
        stop=progress.stop or StopReason.ANSWERED,
        tool_calls=records,
        files=files_touched(records),
        model_calls=tuple(state["model_calls"]),
        tokens=progress.tokens,
        seconds=seconds,
    )


def repo_map(search: DirectSearch) -> str:
    """The root's entries, with each top-level folder's entries indented under it."""
    entries = search.list_files(".").splitlines()

    return "\n".join(chain.from_iterable(_with_children(search, entry) for entry in entries))


def _with_children(search: DirectSearch, entry: str) -> list[str]:
    if not entry.endswith("/"):
        return [entry]

    return [entry, *(f"  {child}" for child in search.list_files(entry).splitlines())]


def files_touched(records: Sequence[ToolCallRecord]) -> tuple[str, ...]:
    """Paths read or outlined, in first-touched order, each once."""
    paths = (
        Call(record.name, record.args).path
        for record in records
        if record.name in FILE_TOOLS and record.outcome is Outcome.RAN
    )

    return tuple(dict.fromkeys(paths))


def record_of(call: Call, output: str, outcome: Outcome) -> ToolCallRecord:
    return ToolCallRecord(call.name, call.args, output, outcome)


def last_reply(state: AgentState) -> AIMessage:
    reply = state["messages"][-1]
    if not isinstance(reply, AIMessage):
        raise TypeError(f"expected the model's reply last, got {type(reply).__name__}")

    return reply


def model_call(reply: AIMessage) -> ModelCall:
    usage = reply.usage_metadata or {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

    return ModelCall(
        prompt_tokens=usage["input_tokens"],
        output_tokens=usage["output_tokens"],
        done_reason=str(reply.response_metadata.get("done_reason", "")),
    )
