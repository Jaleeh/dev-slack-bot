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

`make eval` downloads [django-oscar](https://github.com/django-oscar/django-oscar) at a fixed tag into `.cache/` on the first run. It then scores a retriever on the question set and a redactor on the fake personal data, prints a summary, and saves the numbers and the setup that produced them to `results/`. Both folders are git-ignored. It needs uv and git, and no model or database.

Until the bot exists, it scores a retriever stand-in that returns the answer key, so every retrieval score is 1.000. That proves the scoring works from start to finish.

Until Presidio is added, the redactor is a stand-in that changes nothing. Its catch rate (the share of planted personal data removed) is 0.000, and its wrong-flag rate (the share of look-alikes wrongly removed) is 0.000.

## Grading answers

`make eval-answers` checks the answer grader itself. A local model reads planted answers from `datasets/wrong_answers.yaml` and answers yes or no: does the answer state each key fact, and does it claim anything the code doesn't support? A trustworthy grader passes every correct answer and fails every planted wrong one on the check it was written to fail. A check whose reply can't be read twice in a row is recorded as ungraded, never as a pass.

It needs Ollama running with the model pulled (see the main README), and takes several minutes. It prints whether the grader got each answer right and saves the run, including which model graded it, to `results/answers-<time>.json`. `CHAT_MODEL`, `EVAL_JUDGE_MODEL` and `OLLAMA_BASE_URL` in `.env` choose the model.

## Running the agent

`make eval-agent` runs the real agent once per question and scores two things from that one run:

- **Retrieval:** recall@5, recall@10 and MRR over the files the agent read or outlined, in the order it first touched them. Files that only showed up in grep hits don't count.
- **Answers:** the grader above, on the final answer. Faithfulness is judged against the text the agent's tool calls returned.

**A full run takes about 3 hours.** `make eval-agent IDS="offer-order voucher-guest-rejected"` runs only the named questions. An unknown id stops the run before any model call.

When the agent gives up, the asker gets "I couldn't work this out from the code". That answer isn't graded: it scores 0 on facts, stays out of the faithfulness counts and is counted as **empty**.

The results go to `results/agent-<time>.json`, rewritten after every question. If a run dies partway, the finished questions are kept, and the rest can be rerun with `IDS=`. Each file records the agent and judge settings it ran with.

## Files

| File | Holds |
|---|---|
| `datasets/questions.yaml` | The labelled questions, with the facts and files each answer needs |
| `datasets/pii.yaml` | Fake personal data planted in short texts, and look-alikes a redactor must leave alone |
| `datasets/wrong_answers.yaml` | Right and planted wrong answers to some of the questions, with the code each is based on |
| `dataset_file.py` | Loads a dataset file and names each badly formed entry by its id |
| `question_set.py` | Loads the questions and rejects badly formed entries |
| `pii_set.py` | Loads the fake personal data and rejects badly formed or real-looking entries |
| `retrieval_metrics.py` | recall@k and reciprocal rank |
| `sample_repo.py` | Downloads the sample repository once and reuses it |
| `retriever.py` | The hook a retrieval method plugs into, and the answer-key stand-in |
| `pii_metrics.py` | Catch rate and wrong-flag rate |
| `redactor.py` | The hook a redactor plugs into, and the do-nothing and answer-key stand-ins |
| `runner.py` | Runs a retriever over the questions and a redactor over the personal data, scores both and saves the results |
| `run_record.py` | Reads the commit each run's numbers came from |
| `settings.py` | Which model grades answers, read from `.env` |
| `answer_set.py` | Loads the planted answers and rejects badly formed entries |
| `grader.py` | Asks the model one yes/no question per check and decides whether the grader got an answer right |
| `answer_runner.py` | Grades every planted answer and saves the results |
| `ask.py` | Answers one question with the agent, showing each search and read |
| `agent_scores.py` | Scores one agent run: which questions to run, the files it found, run totals |
| `agent_runner.py` | Runs the agent on the questions, grades its answers and saves the results |

## More

- [Step 2 spec](../../docs/specs/2026-10-24-step-2-evals.md): what each eval measures and why
- [ADR-001](../../docs/adrs/adr-001-how-answers-and-retrieval-are-evaluated.md): why the scoring is written by hand
