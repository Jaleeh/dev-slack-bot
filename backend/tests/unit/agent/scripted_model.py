from collections.abc import Sequence
from typing import Any

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import LanguageModelInput
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatResult
from langchain_core.runnables import Runnable
from pydantic import Field


class ScriptedModel(GenericFakeChatModel):
    """Replies with its scripted messages in turn and keeps every input it was sent.

    LangChain's fake models don't implement bind_tools, so binding only records the tool names,
    which each call reports in `tools_per_call` (empty for an unbound call).
    """

    inputs: list[list[BaseMessage]] = Field(default_factory=list)
    tools_per_call: list[tuple[str, ...]] = Field(default_factory=list)

    def bind_tools(
        self, tools: Sequence[Any], **kwargs: Any
    ) -> Runnable[LanguageModelInput, AIMessage]:
        return self.bind(tool_names=tuple(tool.name for tool in tools))

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        self.inputs.append(list(messages))
        self.tools_per_call.append(kwargs.pop("tool_names", ()))
        return super()._generate(messages, stop, run_manager, **kwargs)


def scripted(*replies: AIMessage | str) -> ScriptedModel:
    return ScriptedModel(messages=iter(replies))
