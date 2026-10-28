# ADR-005: Which model answers questions

## Context and Problem Statement

The bot answers staff questions by searching the code with four tools: list a folder, search text, outline a file and read lines. A model decides which tools to call, reads what they return, and writes the answer. The askers are project managers and support staff, so the answer must be right, based on code the bot actually read, and free of code names.

The model must run locally for now, and it must not be the answer grader's model ([ADR-004](adr-004-how-the-answer-grader-judges-answers.md)), so the bot never grades its own work. A throwaway spike ran the agent on five eval questions to choose it.

## Acceptance Criteria

- Runs on a 16 GB laptop alongside Docker, so the model has about 9 billion parameters or fewer, and needs no API key.
- Reads the code before answering, and makes nothing up.
- Gives the asker an answer or a plain "I couldn't work this out from the code", never an empty reply.
- Several minutes per question is acceptable. Accuracy comes first.

## Considered Options

Each option answered the same five questions once, with the same tools and a 15-call limit.

| | 9B coding model, thinking off | 9B coding model, thinking on | Grader's 4B model, thinking off |
|---|---|---|---|
| Right / partly right / wrong or empty | 2 / 2 / 1 | 3 / 1 / 1 (empty) | 1 / 3 / 1 |
| Time for 5 questions | ~12 min | ~31 min | ~2.5 min |
| Reads the right files | sometimes | yes | never reads a file |

**9B coding model, thinking off**
- Pro: reads the code, and is faster than with thinking on.
- Con: once answered with no searches and made up the details. Once looped on the same call.

**9B coding model, thinking on**
- Pro: reads the most, makes nothing up, and doesn't loop.
- Con: the slowest. Two answers were full of code names even though the prompt forbids them. One answer came back empty.

**The grader's smaller model, thinking off**
- Pro: the fastest.
- Con: answered from search hits alone and never read a file. It is also the grader, so the bot would grade its own work.

## Decision Outcome

The 9B coding model with thinking on answers questions. The model is a setting, so a hosted model can replace it without code changes.

- **A rewrite step removes code names.** The same model, with thinking off and no tools, rewrites the draft in plain English. It keeps every fact and the bug-or-setup verdict, and adds nothing. The prompt rule alone didn't stop code names.
- **At a limit, the tools stay defined.** The model is told to answer with what it has, and any tool call it still makes is not run. The spike's empty answer came from removing the tools at the limit: the model wrote a tool call anyway, which was kept as a call rather than text. Context size wasn't the cause, as the prompt was at 59% and wasn't cut. On replay, keeping the tools defined, turning thinking off for the final call, or sending "answer now" as a system note each gave a correct answer every time. Keeping the tools also keeps the start of the prompt the same, so the model can reuse its cache instead of re-reading the whole prompt.
- **An empty answer becomes the fallback.** If the forced answer still has no text, the asker gets "I couldn't work this out from the code", and the eval counts it as empty.
- **Speed is accepted.** A question takes about 3 to 10 minutes, so a full eval takes about 3 hours, and the eval can run only some of the questions.

Five questions, run once each, is weak evidence. The step 3 baseline eval measures this choice on all 30 questions. Step 7 checks it again with vector search. If the kept-tools fix fails on other questions, turning thinking off for the final call is the next option.
