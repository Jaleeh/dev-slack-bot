from typing import Any

CODE = "# src/oscar/apps/offer/benefits.py\nclass Benefit:\n    pass\n"


def a_question(id_: str, fact_count: int) -> dict[str, Any]:
    return {
        "id": id_,
        "type": "how_it_works",
        "question": "How does this work?",
        "key_facts": [f"Fact {number}." for number in range(1, fact_count + 1)],
        "files": ["src/oscar/apps/offer/benefits.py"],
    }


def a_question_set(*questions: dict[str, Any]) -> dict[str, Any]:
    return {"version": 1, "repo": "django-oscar", "ref": "4.2.1", "questions": list(questions)}


def a_wrong(kind: str, fails: str) -> dict[str, str]:
    return {"kind": kind, "fails": fails, "answer": "A wrong answer."}


EVERY_KIND = [
    a_wrong("wrong_rule", "fact-2"),
    a_wrong("made_up_detail", "faithfulness"),
    a_wrong("vague", "fact-1"),
    a_wrong("other_question", "fact-1"),
]


def an_entry(**overrides: Any) -> dict[str, Any]:
    return {
        "question_id": "q1",
        "code": CODE,
        "correct": "A correct answer.",
        "wrong": EVERY_KIND,
        **overrides,
    }


def an_answer_set(*entries: dict[str, Any]) -> dict[str, Any]:
    return {"version": 1, "answers": list(entries)}
