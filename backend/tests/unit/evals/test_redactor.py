from evals.pii_metrics import PiiMetrics, pii_metrics, score_snippet
from evals.pii_set import PII_PATH, load_pii_set
from evals.redactor import AnswerKeyRedactor, NoRedactor, Redactor


def score_with(redactor: Redactor) -> PiiMetrics:
    snippets = load_pii_set(PII_PATH).snippets
    results = [score_snippet(snippet, redactor.redact(snippet.text)) for snippet in snippets]

    return pii_metrics(snippets, results)


def test_no_redactor_scores_zero_on_the_pii_set() -> None:
    metrics = score_with(NoRedactor())

    assert metrics.catch_rate == 0.0
    assert metrics.wrong_flag_rate == 0.0


def test_answer_key_redactor_scores_full_marks_on_the_pii_set() -> None:
    metrics = score_with(AnswerKeyRedactor(load_pii_set(PII_PATH)))

    assert metrics.catch_rate == 1.0
    assert set(metrics.catch_rate_by_type.values()) == {1.0}
    assert metrics.wrong_flag_rate == 0.0
