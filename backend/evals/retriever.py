"""The seam a retrieval method plugs into, and a stand-in that proves the plumbing."""

from typing import Protocol

from evals.question_set import QuestionSet


class Retriever(Protocol):
    name: str

    def retrieve(self, question: str) -> list[str]:
        """Returns repo-relative paths, most relevant first."""
        ...


class AnswerKeyRetriever:
    """Returns each question's correct files, so a working runner scores it 1.0."""

    name = "answer-key"

    def __init__(self, question_set: QuestionSet) -> None:
        self._files = {question.question: question.files for question in question_set.questions}

    def retrieve(self, question: str) -> list[str]:
        return list(self._files[question])
