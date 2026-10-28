# ADR-002: How the bot finds code to answer a question

## Context and Problem Statement

The bot answers questions about a repository, so it must first find the code that holds the answer. Askers are often non-technical, so many questions use plain words rather than the names in the code. The way the bot searches sets answer quality, token cost, setup effort and what data reaches an embedding provider. One of the project's goals is for its maintainer to learn AI engineering, so building the approach should also cover agent design and retrieval.

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

The options below add to a retrieval method rather than replace one.

**Query rewriting** (the model turns a plain-word question into likely code terms, or a guess at the code, before it searches)
- Pro: needs no index, so it works with direct search and fits a trial. Aims straight at plain-word questions.
- Con: one more model call per question. A wrong guess sends the search the wrong way.

**Plain-language summary index** (the model writes a plain-language summary of each file, and the summaries are embedded instead of the code)
- Pro: plain-word questions are matched against plain words, not code. Summaries are shorter than code, so less code reaches the embedding provider.
- Con: every changed file is summarised again on each refresh, which costs model calls. A summary can leave out the detail a question needs.

**Keyword and vector search merged in one tool** (one ranked list from both, in the same database)
- Pro: finds exact names and plain-word matches in one call. Gives a small model one search tool, not two to choose between. Adds no container.
- Con: the merge needs tuning, and it still needs the vector index.

These options were weighed more briefly:

- **Symbol tools** (find where a name is defined and where it is called): follow leads into callers precisely with no embeddings, but need a parser for each language and give a small model more tools to choose between.
- **Reranking** (a second model reorders the top search results): usually puts the right code nearer the top, but is another model to run, and the local model server may not serve one.
- **Graph of the whole repository** (a model extracts entities and links across every file): can answer questions that span many files, but is costly to build and is rebuilt often as the code changes.
- **Whole files in the prompt** (skip search and send large parts of the repository): nothing to search or index, but a real repository does not fit a local model's context, and every file reaches the chat provider.

## Decision Outcome

An agent with both retrieval methods, selected by a setting. It is the only option that meets every criterion: direct search lets a trial start with nothing, and the agent can follow leads within its per-question limit. The evals pick the default setting, so no method is assumed best before it is measured. A fixed pipeline is not shipped, but it is kept in the evals as a baseline once vector search exists, so every agent mode is measured against the cheapest approach. If the evals show the agent's extra tokens add little accuracy, this ADR should be revisited.

Query rewriting is measured on direct search first, because it needs no index. The merged keyword and vector tool, and the plain-language summary index, are measured with vector search as more settings, on the same questions. Each one is kept only if the evals show it helps. Symbol tools and reranking are deferred until the evals show a gap they would close. A graph of the whole repository and whole files in the prompt are not pursued: the first costs too much to rebuild as the code changes, and the second does not fit a local model.
