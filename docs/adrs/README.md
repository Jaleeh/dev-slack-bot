# Architectural Decision Records (ADRs)

These ADRs record architectural decisions: each is a short, self-contained record of one decision, the options weighed, and why we chose as we did. They exist to steer implementation, keep it consistent, and serve as a defensible audit trail that the design was reasoned through.

ADRs are added as decisions warrant one; this index is not a complete catalogue of every choice the pipeline has made — the slice specs in [`../specs/`](../specs/) carry the rest.

## Format

Each ADR is a sequentially-numbered file, `adr-{number}-{title-kebab-case}.md`, following this template:

```
# ADR-{nnn}: {title}

## Context and Problem Statement
What we need to make a decision about and why

## Acceptance Criteria
Any proposed solution must meet these criteria, otherwise it is an invalid solution

## Considered Options
A list of possible solutions with their pros and cons

## Decision Outcome
Which solution was chosen and why
```

## Index

ADR numbers are assigned in the order ADRs are created, not by topic.

- [ADR-001: How answers and retrieval are evaluated](adr-001-how-answers-and-retrieval-are-evaluated.md)
- [ADR-002: How the bot finds code to answer a question](adr-002-how-the-bot-finds-code-to-answer-a-question.md)
- [ADR-003: How repositories stay up to date](adr-003-how-repositories-stay-up-to-date.md)

## Key considerations

- An ADR is short and concise.
- No code samples — it is about the decision, not the implementation.
- Titles describe what is being decided, not the decision reached, and avoid naming specific technologies where possible.
