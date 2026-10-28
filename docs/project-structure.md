# Project structure

Where code lives and which way imports point. This is a living document: update it in the same change that moves the tree.

> **Status:** partly built. Built so far: `backend/app/{main.py,api,config,db}`, `backend/app/retrieval/direct/` (the search tools), `backend/app/agent/` (the search agent) and `backend/app/config/agent.py` (its settings), `backend/alembic`, `backend/evals/` (retrieval metrics, the question set, the sample repo fetch, the runner, the PII set, PII scoring, the answer grader, `ask.py` and the agent eval `agent_runner.py` so far), `backend/tests/{unit,integration,learning}`, `frontend/`, `Dockerfile`, `docker-compose.yml` and `Makefile`. Each remaining folder is created in the [build order](design-doc.html) step that first needs it.

## Layout

```text
dev-slack-bot/
├── backend/
│   ├── pyproject.toml
│   ├── alembic/                 # DB migrations
│   ├── app/
│   │   ├── main.py              # app setup, serves frontend, security headers
│   │   ├── api/                 # HTTP routes only (thin)
│   │   ├── chat/                # chat adapters: slack/, web/
│   │   ├── agent/               # graph.py, guardrails.py (pure), prompts.py, tools.py
│   │   ├── retrieval/           # direct/ (search tools), service.py, chunking.py (pure), models.py
│   │   ├── privacy/             # service.py, placeholders.py (pure), models.py
│   │   ├── providers/           # chat + embedding model factory
│   │   ├── repos/               # service.py, models.py
│   │   ├── config/              # settings, agent settings, secret encryption
│   │   └── db/                  # session + base only
│   ├── evals/                   # datasets/, runners, ask.py, results/ and .cache/ (git-ignored)
│   └── tests/
│       ├── unit/                # pure logic, fast
│       ├── integration/         # real Postgres; LLM, Slack and GitHub mocked
│       └── learning/            # pins third-party behaviour
├── frontend/
│   └── src/
│       ├── app/                 # routes: setup, chat, settings
│       ├── components/
│       │   ├── setup/           # setup wizard
│       │   ├── chat/            # browser chat
│       │   └── ui/              # shadcn primitives
│       ├── hooks/
│       ├── lib/                 # API client
│       └── styles/tokens.css    # design tokens
├── Dockerfile                   # builds frontend, copies it into the backend image
├── docker-compose.yml           # app + Postgres (+ optional Langfuse)
├── Makefile                     # dev commands: up, dev, down, test, lint, migrate, eval
├── .env.example
├── .github/workflows/           # CI, added once the GitHub repository exists
└── docs/                        # adrs/, specs/, plans/
```

## Rules

### Organise by feature

- Each backend feature folder (`chat/`, `agent/`, `retrieval/`, `privacy/`, `repos/`) owns its own `service.py` and `models.py`.
- `db/` holds only the session and the declarative base, not every model.
- Frontend components sit under `components/<feature>/`; shared primitives go in `components/ui/`.

### Layers and imports

| Layer | Where | Holds |
|---|---|---|
| Entry points | `api/`, `chat/` | Request and response shapes, auth. No business logic. |
| Services | `<feature>/service.py` | Rules and orchestration |
| Pure core | `<feature>/*.py` with no I/O (e.g. `placeholders.py`, `chunking.py`) | Decisions and calculations, testable with plain values |
| Persistence | `<feature>/models.py` | SQLAlchemy mapping only, no behaviour |

Imports point inward: entry points → services → pure core and models. A service never imports from `api/` or `chat/`.

### Tests

- `unit/` tests pure logic per behaviour, not one test file per class.
- `integration/` runs against a real Postgres in Docker. Never mock the database.
- Mock only unmanaged dependencies: model and embedding providers, Slack, GitHub.
- `learning/` pins how third-party libraries behave (Presidio, LangGraph, pgvector) before code depends on them.

## Tooling

Listed in [tech-stack.md](tech-stack.md).
