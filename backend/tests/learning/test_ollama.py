"""Pins how LangChain's Ollama chat model behaves for the answer grader."""

import httpx
import ollama
import pytest
from langchain.chat_models import init_chat_model

from evals.grader import FACT_PROMPT, Verdict
from evals.settings import EvalSettings, build_judge
from tests.support import UNREACHABLE_URL


def test_unreachable_ollama_raises_connect_error() -> None:
    model = init_chat_model("ollama:ornith:9b", base_url=UNREACHABLE_URL)

    with pytest.raises(httpx.ConnectError):
        model.invoke("hi")


def test_unknown_model_raises_response_error(ollama_url: str) -> None:
    model = init_chat_model("ollama:no-such-model:1b", base_url=ollama_url)

    with pytest.raises(ollama.ResponseError) as raised:
        model.invoke("hi")

    assert raised.value.status_code == 404


def ask_judge(fact: str) -> Verdict:
    judge = build_judge(EvalSettings()).with_structured_output(Verdict)
    reply = judge.invoke(
        FACT_PROMPT.format(
            question="With a buy-three-get-one-free deal, how many free items does a customer get?",
            answer="The customer gets one free item per basket, however many they buy.",
            fact=fact,
        )
    )

    assert isinstance(reply, Verdict)
    return reply


@pytest.mark.usefixtures("ollama_judge")
def test_structured_output_returns_a_yes() -> None:
    assert ask_judge("The customer gets one free item per basket.").answer == "yes"


@pytest.mark.usefixtures("ollama_judge")
def test_structured_output_returns_a_no() -> None:
    assert ask_judge("Vouchers can't be used by guest customers.").answer == "no"
