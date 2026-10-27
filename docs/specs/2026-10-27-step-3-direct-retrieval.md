# Step 3: Direct retrieval

**Date:** 2026-10-27
**Status:** approved
**Build order:** step 3 of 7 in the [design doc](../design-doc.html)

## Intent

The first version of the bot. A staff member asks a question in plain English, and an agent searches the code, reads what it needs, and answers on the command line. The askers are project managers and support staff: they want to know how a business rule works, or whether a problem is a bug or a setup issue. They never need file names.

Accuracy comes before speed. An answer that takes several minutes is fine. A fast answer that is wrong, made up or full of code names is not.

Step 3 also gives the step 2 evals their first real numbers. Every later step (the redactor, chat, vector search) is measured against this baseline, and step 7 reuses the same eval to pick the default retrieval method ([ADR-002](../adrs/adr-002-how-the-bot-finds-code-to-answer-a-question.md)).

## Success

When all three slices are merged:

1. `make ask Q="..."` answers a question about the sample repository. While it works, it shows each search and read. At the end it shows the answer and the number of tool calls, tokens and seconds.
2. `make eval-agent` runs the agent on every question in `questions.yaml`, or on the ones named. It scores retrieval and answers from that single run, prints a summary, and saves a results file.
3. One full baseline run is saved, and its numbers are copied into the slice 3.3 plan. There is no pass bar.
4. The maintainer has hand-checked the grader against real answers (deferred from step 2).
5. `make test` and `make lint` pass.

## Goals

- A LangGraph agent with four language-agnostic search tools.
- Guardrails that stop wasted calls, made-up answers and empty answers.
- A last step that rewrites the answer in plain English.
- Per-question limits on tool calls and tokens, set in settings.
- A command-line ask that shows the agent's work.
- An eval run of the real agent, with a filter to run only some questions.

## Non-goals

- **Conversation memory.** Every question stands alone. Step 5 adds memory per chat thread, using the Postgres checkpointer. The thread decides what is related, not the model.
- **Vector or hybrid retrieval.** That's step 7. Only `RETRIEVAL=direct` exists.
- **Real company repositories.** Until the redactor exists (step 4), the bot reads only the public sample repository.
- **Chat, Slack or a browser UI.**
- **A glossary of staff words and code words.** A prompt rule covers this for now.
- **Pass bars, Langfuse, prompt caching.**
- **Changing `make eval`.** It stays the fast run that needs no model.

## Anti-goals

- **Code names in answers.** Function, class, field and file names in a final answer count as a failure, even when the answer is right.
- **Answering without looking.** In the spike, the bot once answered with 0 searches and made up the details.
- **A silent empty answer.** The asker always gets either an answer or a plain "I couldn't work this out from the code".
- **Python-only tools.** Company repositories use many languages. Oscar is only the first test repository.
- **Reading outside the repository.** A tool path that leaves the repository root (through `..`, an absolute path or a symlink) is refused.

## Decided in the spike

A throwaway spike (2026-10-27, git-ignored, not committed) ran the agent on 5 questions to choose its model. Full results go in ADR-005 (see 3.2).

| | ornith:9b, thinking off | ornith:9b, thinking on | gemma4:e4b, thinking off |
|---|---|---|---|
| Right / partly right / wrong or empty | 2 / 2 / 1 | 3 / 1 / 1 (empty) | 1 / 3 / 1 |
| Time for 5 questions | ~12 min | ~31 min | ~2.5 min |
| Reads the right files | sometimes | yes | never reads a file |

- **Model: `ornith:9b` with thinking on.** It is the most accurate. It is also not the grader's model (`gemma4:e4b`), so the bot doesn't grade its own work.
- **Speed is accepted.** It takes about 3–10 min per question, so a full 30-question eval takes about 3 hours. That's why the eval can run only some of the questions.
- **The prompt alone didn't hold.** With thinking on, two of five answers were full of code names even though the prompt forbids them. That's why there's a rewrite step.
- **Wasted calls.** The bot repeated identical calls, read folders as files, used whole calls on files that only point to another file, and needed about 7 calls to read one 1,400-line file 200 lines at a time.
- **The empty answer.** The spike already told the model "Answer now" with tools off when it hit the call limit, and the answer still came back empty. The cause isn't known. Overflowing the model's 32k context is a likely suspect after ~10 file reads, but that is unconfirmed. Slice 3.2 finds the cause before choosing the fix.

## Slices

Each slice is one branch and one PR. One plan per slice goes in `docs/plans/`, written just before the slice starts.

| Slice | Branch | Delivers |
|---|---|---|
| 3.1 | `step-3.1-search-tools` | The four search tools, language-agnostic, with learning tests |
| 3.2 | `step-3.2-agent` | Agent, guardrails, rewrite step, settings, `make ask`, ADR-005 |
| 3.3 | `step-3.3-agent-evals` | `make eval-agent`, question filter, baseline run, grader hand-check |

Order: 3.1 → 3.2 → 3.3. This spec lands first, on the `step-3-spec` branch.

### Layout

Following [project-structure.md](../project-structure.md):

```text
backend/app/
├── retrieval/
│   └── direct/          # 3.1: the four tools over a repository folder; path checks and filtering are pure
├── agent/
│   ├── graph.py         # 3.2: LangGraph agent and rewrite step
│   ├── guardrails.py    # 3.2: pure decisions (repeat, re-read, limits)
│   └── prompts.py       # 3.2
└── config/              # 3.2: agent settings
backend/evals/
├── ask.py               # 3.2: make ask
└── agent_runner.py      # 3.3: make eval-agent
```

The names are suggestions. The builder may rename them, as long as the pure parts stay free of I/O.

---

### 3.1 Search tools

Four tools. Each takes paths relative to the repository root and returns plain text for the model.

| Tool | Does |
|---|---|
| `list_files(path)` | Lists the files and folders directly inside a folder |
| `grep(pattern, path)` | Case-insensitive regex over every text file under `path`. Hits are grouped by file with a count per file, show 1–2 lines of context, and are capped (the spike used 40). |
| `read_file(path, start_line, end_line)` | Returns numbered lines, at most 200 per call. Calling it on a folder returns the folder's listing instead of an error. |
| `outline(path)` | Lists a file's classes, functions and methods with their line numbers, so the agent reads only the part it needs |

**Language-agnostic:**
- `grep` searches every text file, not only `.py`. It skips binary files.
- Every tool respects the repository's `.gitignore`.
- A noise list is skipped by every tool. It is a setting (`SEARCH_SKIP`, glob patterns). The defaults are migrations, vendored folders (`node_modules`, `vendor`), lock files and minified files. *Our call.*
- `outline` uses tree-sitter through `tree-sitter-language-pack`, which has ready-built grammars for 372 languages. Each grammar downloads the first time its language is used, so the Docker image must prefetch them (step 5). For a file it can't parse, it says so, and the agent falls back to `read_file`.
- **Docs are searchable.** `grep` and `read_file` reach Markdown, reStructuredText and plain-text docs like any other text file.

**Candidate library:** `grep-ast`, by the author of Aider. It shows each grep hit inside the function or class that holds it. Adopt it only if the learning tests show it fits. Otherwise build a plain grep with context lines.

**Safety:** every path is resolved and refused if it leaves the repository root. A bad regex returns an error message to the model, not an exception.

**Errors** go back to the model as text it can act on (`no such file`, `not a folder`, `bad pattern`), never as a crash.

**Dependencies:** `tree-sitter-language-pack`, `pathspec` (for `.gitignore`), and `grep-ast` if adopted.

**Tests:**
- Unit tests run against a tiny fixture repository built inside the test. It has files in at least two languages (Python and TypeScript), a `.gitignore`, a migrations folder, a binary file, a doc file, and a symlink that points outside the root. They check what each tool returns, what gets skipped, and that every escape route is refused.
- Learning tests pin `tree-sitter-language-pack` outlines for Python and TypeScript, and `grep-ast` output if it's a candidate.

---

### 3.2 Agent

**Shape.** A LangGraph agent loop, then a separate rewrite step:

1. **Search loop:** `CHAT_MODEL` with thinking on and the four tools, until it answers or hits a limit.
2. **Rewrite:** the same model with thinking off and no tools. It gets the question and the draft answer, and rewrites the draft in plain English. It must keep every fact and the bug-or-setup verdict, add nothing, and remove every code name. *Thinking off here is our call, since it only rewrites.*

Before writing your own loop or guardrails, check the agent helpers in LangChain 1.x and LangGraph (for example, built-in tool-call limits). Use them where they fit, and note the choice in the plan.

**Prompt.** It carries over the spike's rules:
- Use the tools before answering.
- Staff use everyday words that may not match the code, so try other words and look at folder names.
- Base every claim on code that was read, and say when you're not sure.
- Use plain English.
- For a reported problem, say whether it's a bug or a setup issue, why, and how to fix it.
- Docs show where to look. The code decides when the two disagree.

It also gives the top two folder levels of the repository, with noise skipped, so the agent starts with a map. *Our call.* The spike's Oscar-only map is replaced.

**Guardrails.** These are pure decisions, unit-tested with plain values:

| Guardrail | Rule |
|---|---|
| Search first | A reply with no tool calls before any `grep`, `read_file` or `outline` call is sent back once with "Search the code before answering." A `list_files` call alone doesn't count, because it reads no code. *Our call.* |
| Repeat call | An identical call (same tool, same arguments) is blocked with a message. A second blocked repeat ends the loop and moves on to the final answer. |
| Re-read | A `read_file` whose lines were all returned already, and are still in the model's context, is blocked with a message. If the empty-answer fix trims old tool output, trimmed lines can be read again. *Our call.* |
| Tool-call limit | At `AGENT_MAX_TOOL_CALLS`, tools are removed and the model is told to answer with what it has |
| Token limit | At `AGENT_MAX_TOKENS` (prompt plus completion, summed over the question), the same as the tool-call limit |
| Empty answer | Find the cause first (see below). If the final answer is still empty, the asker gets "I couldn't work this out from the code," and the run records it as empty. |

**The empty answer, first task of the slice.** Reproduce the spike's empty answer to `voucher-guest-rejected`. Record the prompt's token count against the context size on every model call, and find out why the answer is empty. The fix depends on the cause. If the context is overflowing, options include a larger context, shorter tool output, or trimming old tool output. The cause and the fix go in the plan and ADR-005.

The 3.2 plan is written in two parts. *Our call.* Part one covers this investigation. Part two covers everything else, written once the cause is known, because the fix can change the tool caps, the settings and the guardrails.

**Settings.** These go in a settings class that needs no database, so `make ask` and the evals run without Postgres. The app's `Settings` requires `DATABASE_URL`. `EvalSettings` should read `CHAT_MODEL` from the same place rather than repeat it. *Our call.*

| Variable | Default | Meaning |
|---|---|---|
| `CHAT_MODEL` | `ollama:ornith:9b` | Exists already. Now drives the agent. |
| `AGENT_THINKING` | `true` | Thinking in the search loop |
| `AGENT_MAX_TOOL_CALLS` | `15` | Per question |
| `AGENT_MAX_TOKENS` | `1000000` | Per question. High on purpose: local models cost nothing. Tighten it from the eval's numbers before a paid provider is used. *Our call on the value.* |
| `AGENT_CONTEXT_TOKENS` | `32768` | Context size passed to Ollama (the spike's value) |
| `RETRIEVAL` | `direct` | The only value in step 3. Anything else stops with a clear message. |
| `SEARCH_SKIP` | see 3.1 | Noise globs |

Add them to `.env.example`.

**Which repository.** The agent takes the repository folder as an argument, not as a setting. *Our call.* In step 3 the only repository is the sample, so `make ask` and `make eval-agent` both get it from the existing sample-repo fetch (`evals/sample_repo.py`), which matches `questions.yaml`'s `repo` and `ref`. An eval can't score against the wrong code that way, and `app/` never imports from `evals/`. The `make ask` entry point therefore lives in `evals/`. Step 4 or 5 adds a repository setting when real repositories arrive.

**Result.** For each question, the agent returns:
- the final answer, and the draft before the rewrite
- the tool calls in order
- the files read or outlined, in first-touched order
- the text the tools returned
- tool calls, tokens and seconds
- whether a limit or guardrail ended the loop

`make ask` and the eval both use this.

**`make ask Q="..."`.** Fetches the sample repository on first use, as `make eval` does. Prints each tool call as it happens, then the draft, the final answer, and the stats. It shows the draft so a fact lost in the rewrite is easy to spot. *Our call.* It stops with a clear message if Ollama isn't reachable (the same style as `eval-answers`).

**Dependencies.** `langgraph`, plus `langchain` and `langchain-ollama`, which move from the dev group to the main dependencies.

**Tests:**
- Unit tests cover the guardrail decisions with plain values.
- Unit tests run the agent loop with LangChain's fake chat model scripted to make tool calls. Search-first, the blocked repeat, both limits, the empty-answer fallback and the rewrite step each have a test. The model is an unmanaged dependency, so faking it is right.
- Learning tests pin LangGraph tool calling with `ChatOllama` and thinking on. They are skipped, with the reason printed, when Ollama isn't reachable.

**Docs:**
- *ADR-005: Which model answers questions.* It records the spike's options, results and the choice, and the empty-answer cause.
- `tech-stack.md`: the agent settings, tree-sitter, and `grep-ast` if adopted.
- `project-structure.md`: what now exists.
- README: `make ask`.
- The design doc's step 3 row and agent section name the four tools.

---

### 3.3 Agent eval

**One run, two scores.** `make eval-agent` runs the agent once per question. From that single run it scores:

- **Retrieval:** recall@5, recall@10 and reciprocal rank (step 2.1). The ranked list is the files the agent read or outlined, in first-touched order. *Our call:* files that only showed up in grep hits don't count.
- **Answers:** the step 2.6 grader on the final answer. That's fact score per question, plus faithfulness. Faithfulness uses the text the tools returned as the code.

Running retrieval and answers separately would double a 3-hour run. That's why one run feeds both.

**Fallback answers** ("I couldn't work this out from the code") are not sent to the grader. Each one scores 0 on facts, sits outside the faithfulness counts, and is counted as **empty**. "Empty" means every question where the asker got the fallback. *Our call.* The rule is fixed now so later runs compare fairly with the baseline.

**Question filter.** `make eval-agent IDS="offer-order voucher-guest-rejected"` runs only those questions. With no filter, it runs all 30. An unknown id stops the run before any model call.

**Results file.** It goes in `results/agent-<UTC timestamp>.json`, in the same style as the step 2 records.

| Field | Holds |
|---|---|
| Run setup | `started_at`, `git_commit`, dataset version, `repo`, `ref`, the question filter, and every agent setting from 3.2, including the model, the judge model and `SEARCH_SKIP` |
| Metrics | Mean recall@5, recall@10, MRR, mean fact score, faithfulness counts, inconclusive count, empty answers, total and mean seconds and tokens |
| Per question | Id, files in order, recall@5/@10, reciprocal rank, every check result, draft and final answer, tool calls, tokens, seconds, what ended the loop |

Progress is logged after each question, as `eval-answers` does. A full run takes hours, so the results file is rewritten after every question. If a run dies partway, the finished questions are kept, and the rest can be rerun with `IDS=`. There's no resume feature. *Our call.*

**The grader's input can be large.** All the tool output for one question can exceed the judge's comfortable context. Measure it on the baseline run. If it's too large, judge faithfulness on the `read_file` and `outline` output only, and note that in the plan. *Our call.*

**Baseline run.** The maintainer runs the full eval once. The numbers go in the 3.3 plan. Then a second run with docs added to `SEARCH_SKIP` shows whether docs help. Both runs are part of 3.3. Docs stay searchable unless the docs-off run is better by more than noise: at least 3 more questions with every fact stated, and no drop in recall@5. That bar allows for the grader's verdicts flipping between runs (ADR-004). If docs-off wins, the default noise list changes in the same PR. *Our call.*

**Grader hand-check** (deferred from step 2). The maintainer reads about 10 graded answers from the baseline run and marks where they disagree with the grader. Any disagreement is noted in the plan. If there are many, ADR-004 is revisited.

**Tests:**
- An integration test runs the runner with a fake agent and a fake judge, using the existing fakes, and checks the results file and its metrics.
- A unit test turns an agent result into a ranked file list.
- The filter's unknown-id rule has a test.

**Docs:** README and `evals/README.md` get `make eval-agent`, with a warning that a full run takes hours.

## Builder's calls

These are open. Choose and note the choice in the plan.

- Module and function names, within the layout above.
- The exact prompt and rewrite wording, within the rules above.
- How `grep` lays out its output, and its exact caps.
- The noise list's exact default patterns.
- Whether to use LangChain or LangGraph helpers or a hand-written loop for the guardrails.
- The summary table layouts.
