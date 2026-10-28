"""Scores one agent run per question: which files it found and how its answer was graded."""

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from statistics import fmean

from pydantic import BaseModel, ConfigDict, computed_field

from app.agent.graph import AgentResult
from app.agent.guardrails import Outcome
from evals.answer_set import FAITHFULNESS
from evals.grader import CheckOutcome, CheckResult, fact_score, is_inconclusive
from evals.question_set import Question, QuestionSet
from evals.retrieval_metrics import recall_at_k, reciprocal_rank


class UnknownQuestions(ValueError):
    def __init__(self, ids: tuple[str, ...]) -> None:
        super().__init__(f"no question with id {', '.join(ids)} in the question set")
        self.ids = ids


@dataclass(frozen=True)
class Attempt:
    result: AgentResult
    checks: tuple[CheckResult, ...]
    evidence: str


class ToolCallEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    args: dict[str, object]
    outcome: str


class QuestionScore(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    files: tuple[str, ...]
    recall_at_5: float
    recall_at_10: float
    reciprocal_rank: float
    checks: tuple[CheckResult, ...]
    is_empty: bool
    draft: str
    answer: str
    tool_calls: tuple[ToolCallEntry, ...]
    tokens: int
    seconds: float
    stop: str
    evidence_chars: int

    @computed_field  # type: ignore[prop-decorator]
    @property
    def fact_score(self) -> float:
        return 0.0 if self.is_empty else fact_score(self.checks)

    @property
    def faithfulness(self) -> CheckOutcome | None:
        return next((c.outcome for c in self.checks if c.check == FAITHFULNESS), None)


class FaithfulnessCounts(BaseModel):
    model_config = ConfigDict(frozen=True)

    passed: int
    failed: int
    unclear: int
    ungraded: int


class AgentMetrics(BaseModel):
    model_config = ConfigDict(frozen=True)

    recall_at_5: float
    recall_at_10: float
    mrr: float
    fact_score: float
    all_facts_stated: int
    faithfulness: FaithfulnessCounts
    inconclusive: int
    empty: int
    seconds_total: float
    seconds_mean: float
    tokens_total: int
    tokens_mean: float


def select_questions(question_set: QuestionSet, ids: Sequence[str]) -> tuple[Question, ...]:
    """The named questions in dataset order, or every question when `ids` is empty."""
    known = {question.id for question in question_set.questions}
    unknown = tuple(dict.fromkeys(id_ for id_ in ids if id_ not in known))
    if unknown:
        raise UnknownQuestions(unknown)

    wanted = set(ids) or known

    return tuple(question for question in question_set.questions if question.id in wanted)


def evidence(result: AgentResult) -> str:
    """The text the tools returned on calls that ran: the code an answer is judged against."""
    return "\n\n".join(
        f"# {record.signature}\n{record.output}"
        for record in result.tool_calls
        if record.outcome is Outcome.RAN
    )


def score(question: Question, attempt: Attempt) -> QuestionScore:
    result = attempt.result
    relevant = set(question.files)
    ranked = list(result.files)

    return QuestionScore(
        id=question.id,
        files=result.files,
        recall_at_5=recall_at_k(ranked, relevant, 5),
        recall_at_10=recall_at_k(ranked, relevant, 10),
        reciprocal_rank=reciprocal_rank(ranked, relevant),
        checks=attempt.checks,
        is_empty=result.is_empty,
        draft=result.draft,
        answer=result.answer,
        tool_calls=tuple(
            ToolCallEntry(name=call.name, args=dict(call.args), outcome=call.outcome.value)
            for call in result.tool_calls
        ),
        tokens=result.tokens,
        seconds=result.seconds,
        stop=result.stop.value,
        evidence_chars=len(attempt.evidence),
    )


def agent_metrics(scores: Sequence[QuestionScore]) -> AgentMetrics:
    """Run totals; fallback answers count as 0 on facts and stay out of the judge's counts."""
    graded = [scored for scored in scores if not scored.is_empty]
    faithfulness = Counter(scored.faithfulness for scored in graded)

    return AgentMetrics(
        recall_at_5=fmean(scored.recall_at_5 for scored in scores),
        recall_at_10=fmean(scored.recall_at_10 for scored in scores),
        mrr=fmean(scored.reciprocal_rank for scored in scores),
        fact_score=fmean(scored.fact_score for scored in scores),
        all_facts_stated=sum(scored.fact_score == 1.0 for scored in graded),
        faithfulness=FaithfulnessCounts(
            passed=faithfulness["pass"],
            failed=faithfulness["fail"],
            unclear=faithfulness["unclear"],
            ungraded=faithfulness["ungraded"],
        ),
        inconclusive=sum(is_inconclusive(scored.checks) for scored in graded),
        empty=len(scores) - len(graded),
        seconds_total=sum(scored.seconds for scored in scores),
        seconds_mean=fmean(scored.seconds for scored in scores),
        tokens_total=sum(scored.tokens for scored in scores),
        tokens_mean=fmean(scored.tokens for scored in scores),
    )
