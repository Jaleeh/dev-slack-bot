from collections.abc import Callable
from typing import Any

from langchain_core.language_models import FakeListChatModel, LanguageModelInput
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.runnables import Runnable, RunnableLambda
from pydantic import BaseModel

YES = '{"answer": "yes"}'
NO = '{"answer": "no"}'


class FakeJudge(FakeListChatModel):
    """Replies with its responses in turn, read the way ChatOllama reads structured output.

    LangChain's fake models don't implement with_structured_output. ChatOllama's json_schema
    method pipes the model into a PydanticOutputParser, so this does the same.
    """

    def with_structured_output(
        self, schema: dict[str, Any] | type, *, include_raw: bool = False, **kwargs: Any
    ) -> Runnable[LanguageModelInput, dict[str, Any] | BaseModel]:
        return self | PydanticOutputParser(pydantic_object=schema)


class FunctionJudge(FakeListChatModel):
    """Answers each prompt with `reply(prompt)`, standing in for a provider's structured output."""

    responses: list[str] = []
    reply: Callable[[Any], Any]

    def with_structured_output(
        self, schema: dict[str, Any] | type, *, include_raw: bool = False, **kwargs: Any
    ) -> Runnable[LanguageModelInput, dict[str, Any] | BaseModel]:
        return RunnableLambda(self.reply)
