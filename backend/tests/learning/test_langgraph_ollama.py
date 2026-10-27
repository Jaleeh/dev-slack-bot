"""Pins how ChatOllama calls tools with thinking on, for the search agent."""

from langchain_core.messages import AIMessage
from langchain_core.tools import tool
from langchain_ollama import ChatOllama


@tool
def read_file(path: str, start_line: int = 1, end_line: int = 200) -> str:
    """Read numbered lines start_line to end_line of a file."""
    return ""


def ask(model: str, ollama_url: str, prompt: str) -> AIMessage:
    llm = ChatOllama(model=model, base_url=ollama_url, reasoning=True, temperature=0)
    reply = llm.bind_tools([read_file]).invoke(prompt)

    assert isinstance(reply, AIMessage)
    return reply


def test_thinking_model_calls_a_bound_tool_with_typed_arguments(
    ollama_chat_model: str, ollama_url: str
) -> None:
    reply = ask(ollama_chat_model, ollama_url, "Read lines 1 to 5 of a.py.")

    assert reply.tool_calls[0]["name"] == "read_file"
    assert isinstance(reply.tool_calls[0]["args"]["start_line"], int)
    assert reply.additional_kwargs["reasoning_content"]


def test_reply_reports_token_usage(ollama_chat_model: str, ollama_url: str) -> None:
    reply = ask(ollama_chat_model, ollama_url, "Say hi. Don't call any tools.")

    assert reply.usage_metadata is not None
    assert reply.usage_metadata["input_tokens"] > 0
    assert reply.response_metadata["done_reason"] == "stop"
