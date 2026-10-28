# ADR-001: How answers and retrieval are evaluated

## Context and Problem Statement

The evals score retrieval, answers and redaction before and after every change, and they pick the default retrieval setting. The design doc left the scoring approach open between two eval frameworks. One of the project's goals is for its maintainer to learn AI engineering, so how each score is produced matters as much as the score itself.

## Acceptance Criteria

- Every score can be explained line by line.
- Runs locally with no hosted service.
- Works with any LangChain chat model, including a local Ollama model.
- The datasets stay in this repository.

## Considered Options

**Ragas** (a Python eval library)
- Pro: ready-made metrics, including faithfulness and answer correctness, and widely used.
- Con: its grading prompts and maths sit inside the library, so a score is hard to explain. Its metrics are tuned for strong hosted models.

**promptfoo** (a config-driven eval tool)
- Pro: good at comparing prompts and models side by side.
- Con: a JavaScript and YAML tool beside a Python backend, built around comparing prompts rather than scoring retrieval.

**Hand-written scoring**
- Pro: every metric is a few lines of tested Python, the grading prompt is ours to read and tune, and it fits the project's stack.
- Con: more work. The AI grader is unproven until it is checked against the maintainer's own grades.

## Decision Outcome

Hand-written scoring. It meets every criterion, and it serves the learning goal by keeping nothing hidden. The AI grader asks yes/no questions per key fact rather than giving a score from 1 to 10, and it is checked once against the maintainer's own grades. Ragas may be added later as a cross-check on the grader, not as a replacement.
