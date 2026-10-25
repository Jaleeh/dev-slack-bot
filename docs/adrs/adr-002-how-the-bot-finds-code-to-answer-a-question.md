# ADR-002: How the bot finds code to answer a question

## Context and Problem Statement

The bot answers questions about a repository, so it must first find the code that holds the answer. Askers are often non-technical, so many questions use plain words rather than the names in the code. The way the bot searches sets answer quality, token cost, setup effort and what data reaches an embedding provider. One of the project's goals is for its maintainer to learn AI engineering, so the approach should also teach agent design and retrieval.

## Acceptance Criteria

- A trial can start with no index and no embedding provider.
- The bot can look at more than one place before it answers, such as a function and the code that calls it.
- Every question stays within its limit on tool calls and tokens.
- Retrieval methods can be compared on the eval set, and the evals pick the default.
- Every call to a chat or embedding provider passes through the PII redactor.

## Considered Options

**Fixed pipeline** (embed the question, fetch the top chunks once, then answer)
- Pro: one model call per question, so cost and speed are predictable. The most common setup and the simplest to build.
- Con: needs an index before the first question, so a trial cannot start empty. Searches once, so it cannot follow a lead into another file. Chunks can split code mid-function.

**Agent with repository search only** (the agent calls tools to search and read files in the clone)
- Pro: no index and no embedding provider, so it fits a trial. Exact names are found reliably, and the agent reads whole files and follows leads.
- Con: weak on plain-word questions that share no words with the code. Can spend more tokens per question.

**Agent with vector search only** (the agent calls a tool that searches embedded code chunks)
- Pro: good at plain-word questions. Fewer tokens per question than reading files.
- Con: needs an index and an embedding provider, so a trial cannot start empty. Code chunks reach the embedding provider during indexing. Results lag the code until the index refreshes.

**Agent with both, selected by a setting** (direct, vector, or hybrid where the agent gets every tool and picks per step)
- Pro: a trial starts on direct search, and the evals measure all three on the same questions. Serves the learning goal by building both methods.
- Con: two retrieval methods to build and maintain. Hybrid has the highest cost and setup, and the agent can pick the wrong tool.

## Decision Outcome

An agent with both retrieval methods, selected by a setting. It is the only option that meets every criterion: direct search lets a trial start with nothing, and the agent can follow leads within its per-question limit. The evals pick the default setting, so no method is assumed best before it is measured. A fixed pipeline is not shipped, but it is kept in the evals as a baseline once vector search exists, so every agent mode is measured against the cheapest approach. If the evals show the agent's extra tokens buy little accuracy, this ADR should be revisited.
