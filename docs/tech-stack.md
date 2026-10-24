# Tech stack

Every tool the project uses, what it is for, and what was rejected. This is the single list: other documents link here instead of copying it. Update it in the same change that adds, removes or swaps a tool.

The reasoning behind the larger choices lives in the [design doc](design-doc.html). Where code lives is in [project-structure.md](project-structure.md).

Versions: the newest stable release of each tool that works with the rest. Exact versions live in the lockfiles.

## Runtime

| Area | Tool | Purpose |
|---|---|---|
| Backend | FastAPI (Python) | HTTP API; also serves the built admin UI |
| Agent | LangGraph | Tool-calling agent; human-in-the-loop `interrupt` for future write confirms |
| Model providers | LangChain chat integrations via `init_chat_model` (`langchain-anthropic`, `langchain-aws`, `langchain-openai`, `langchain-ollama`) | One setting selects Anthropic, OpenAI, Bedrock, Azure OpenAI, Vertex or Ollama |
| Embeddings | LangChain embedding integrations | Separate `EMBEDDING_PROVIDER` setting: Ollama (`nomic-embed-text`), Bedrock (Titan, Cohere), OpenAI |
| Database | Postgres | Settings, encrypted secrets, conversation state, PII mappings |
| Vector store | pgvector via `langchain-postgres` | Vector retrieval inside the same Postgres |
| Conversation state | LangGraph Postgres checkpointer | One chat thread maps to one LangGraph thread |
| ORM and migrations | SQLAlchemy, Alembic | Schema and migrations |
| PII redaction | Microsoft Presidio with a spaCy model | Detects PII and secrets locally; typed placeholders and restore |
| Chat | Slack Bolt for Python, Socket Mode | Slack adapter with no public URL |
| GitHub | GitHub App, shallow `git` clones | Repository access and scheduled refresh |
| Admin UI | Next.js static export, shadcn/ui, Tailwind | Setup wizard, settings, browser chat |
| Tracing | Langfuse (optional, self-hostable) | Tokens, cost and latency per question |

## Quality

| Area | Backend | Frontend |
|---|---|---|
| Package manager | uv | pnpm |
| Lint and format | Ruff | ESLint, Prettier |
| Types | mypy | TypeScript strict |
| Tests | pytest | Vitest |

Evals score a labelled question set on recall@k, MRR, faithfulness, redaction catch rate, cost and latency. Scoring is hand-written ([ADR-001](adrs/adr-001-how-answers-and-retrieval-are-evaluated.md)). Ragas may be added later as a cross-check.

## Packaging and CI

| Area | Tool | Purpose |
|---|---|---|
| Local and self-hosted run | Docker Compose | Two required services (app, Postgres), Langfuse as an optional profile |
| Dev commands | Make | One entry point (`make up`, `make test`, ...) wrapping Docker Compose |
| Images | GitHub Container Registry | Published app image |
| CI | GitHub Actions | Lint, types, tests, retrieval evals. Added once the GitHub repository exists. |

## Rejected

| Tool | Rejected for | Why |
|---|---|---|
| LiteLLM | Model providers | Duplicates the LangChain integrations LangGraph already uses |
| LangSmith | Tracing | Hosted service; data would leave the company's infrastructure |
| SQLite, sqlite-vec | Database | Postgres with pgvector is the industry standard and closer to what companies run |
| Hand-built agent loop | Agent | LangGraph chosen as the widely used framework |
| Realistic fake data | PII stand-ins | Typed placeholders restore exactly and never collide with real names in code |
