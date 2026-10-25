# ADR-003: How repositories stay up to date

## Context and Problem Statement

The bot answers from local clones of each repository and, with vector search, from an index built from those clones. Both must follow the code as it changes, or answers describe code that no longer exists. The first release needs no public URL and runs as two containers, the app and Postgres, so the way the bot learns about changes is constrained.

## Acceptance Criteria

- Needs no public URL.
- Adds no container to the required stack.
- An admin can trade freshness against load and cost.
- Only changed files are re-indexed, so a refresh does not re-embed the whole repository.
- Two refreshes of one repository never run at once, and running a refresh again leaves the same index, with no duplicate chunks.
- Every chunk passes through the PII redactor before it reaches the embedding provider.

## Considered Options

**Webhooks** (GitHub calls the bot on every push)
- Pro: changes arrive within seconds, and nothing runs while the code is idle.
- Con: needs an HTTPS endpoint reachable from the internet, which the first release rules out.

**Change stream into the database** (a source emits change events that a pipeline writes into the index, as DynamoDB Streams feeds OpenSearch)
- Pro: near real time, with no polling.
- Con: a git repository emits no change stream, so it still needs webhooks to start. A pipeline service or queue adds a container, and the redactor must still sit between the code and the embedding provider.

**Scheduled polling** (pull each clone on an interval, then re-index the files that changed)
- Pro: outbound connections only, no extra container, and embedding calls are grouped into batches.
- Con: answers can be up to one interval behind the code.

**Manual refresh only** (an admin presses a button)
- Pro: the simplest to build, and nothing runs unless asked.
- Con: the index goes stale whenever the admin forgets.

## Decision Outcome

Scheduled polling on an interval the admin can change, re-indexing only changed files, plus a manual refresh in the admin UI. Polling is the only option that meets every criterion on its own. Code changes arrive in bursts a few times a day, so a short interval is close enough for people asking how the code works. Manual refresh covers the gap after an urgent change, such as a hotfix the bot should know about before the next interval. Both run the same refresh, which holds a lock per repository, so a manual refresh during a scheduled one cannot run alongside it. Re-indexing a file replaces its chunks rather than adding to them, so a repeated or interrupted refresh leaves no duplicates. Which lock, and whether a second request waits or is skipped, are left to the step 7 spec. The indexer takes a list of changed files as its input, so a webhook can trigger it later without changing it, if a later release adds a public URL. Where the scheduler runs, and what a question sees while an index is being rebuilt, are left to the step 7 spec.
