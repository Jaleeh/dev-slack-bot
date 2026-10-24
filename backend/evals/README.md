# Evals

Evals score how good the bot's output is: whether retrieval finds the right files, whether the redactor catches personal data, and whether answers are right. Choices like direct or vector retrieval, or which model to use, rest on these numbers instead of on guesswork.

This folder is not part of the app. The Docker image doesn't include it.

## Evals and tests

| | Tests (`make test`) | Evals (`make eval`) |
|---|---|---|
| Asks | Does the code do what it should? | How good is the bot's output? |
| Gives | Pass or fail | A score, such as recall@5 = 0.73 |
| Same input, same result | Always | Not once a model is involved |
| Runs | On every change | When comparing options or checking a change |

Runs record numbers only. Pass marks come later, once there are real numbers to set them from.

## The sample repository

django-oscar is a stand-in codebase for the bot to search. None of its code is committed, and nothing outside this folder uses it. Each question in `datasets/questions.yaml` lists the oscar files that hold its answer. A retriever scores well when those files come back near the top.

It's a fixed, public Django codebase, so every retrieval method gets scored against the same files and the scores can be compared fairly.

## Running

`make eval` downloads [django-oscar](https://github.com/django-oscar/django-oscar) at a fixed tag into `.cache/` on the first run. It then scores a retriever on the question set, prints a summary, and saves the numbers and the setup that produced them to `results/`. Both folders are git-ignored. It needs uv and git, and no model or database.

Until the bot exists, it scores a stand-in that returns the answer key, so every score is 1.000. That proves the scoring works from start to finish.

## Files

| File | Holds |
|---|---|
| `datasets/questions.yaml` | The labelled questions, with the facts and files each answer needs |
| `datasets/pii.yaml` | Fake personal data planted in short texts, and look-alikes a redactor must leave alone |
| `dataset_file.py` | Loads a dataset file and names each badly formed entry by its id |
| `question_set.py` | Loads the questions and rejects badly formed entries |
| `pii_set.py` | Loads the fake personal data and rejects badly formed or real-looking entries |
| `retrieval_metrics.py` | recall@k and reciprocal rank |
| `sample_repo.py` | Downloads the sample repository once and reuses it |
| `retriever.py` | The hook a retrieval method plugs into, and the answer-key stand-in |
| `runner.py` | Runs a retriever over the questions, scores it and saves the results |

## More

- [Step 2 spec](../../docs/specs/2026-10-24-step-2-evals.md): what each eval measures and why
- [ADR-001](../../docs/adrs/adr-001-how-answers-and-retrieval-are-evaluated.md): why the scoring is written by hand
