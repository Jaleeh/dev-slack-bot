# Step 1: Skeleton

**Date:** 2026-10-17
**Status:** approved
**Build order:** step 1 of 7 in the [design doc](../../design-doc.html)

## Intent

Get a working local dev setup before any bot features exist. One command starts the backend, the admin UI and Postgres together, and a page in the browser shows they are connected. Every later step builds on this stack, so it should be small, boring and easy to trust.

## Success

1. `make up` on a fresh clone with only Docker and Make installed starts the stack.
2. Opening `http://localhost:8000` shows a status page that reports the backend and the database as connected.
3. Stopping Postgres (`docker compose stop db`) and reloading the page shows the database as down. The page itself still loads.
4. `make test` and `make lint` pass.

## Goals

- FastAPI app with a health route that checks the database.
- Next.js static export, built into the app image and served by FastAPI.
- Postgres with pgvector, and Alembic set up with a baseline migration.
- Docker Compose with two services: `app` and `db`.
- A Makefile as the single entry point for dev commands.
- The folder layout from [project-structure.md](../project-structure.md), created only as far as this step needs.

## Non-goals

- **CI.** It waits until the project has a GitHub repository. The local setup comes first.
- Admin login, settings, secrets and encryption. These belong to later steps.
- Langfuse and the optional Compose profile.
- Publishing images to GHCR.
- Feature folders with no code yet (`agent/`, `retrieval/`, `privacy/`, `repos/`, `chat/`, `providers/`). Create each one in the step that first needs it.
- Hot reload inside containers. Code changes are picked up by running `make up` again.

## Anti-goals

- A status page that looks like a default template. It should look like it belongs with the design doc.
- A health check that always says "ok". It must actually reach Postgres.
- An app that crashes when the database is down. It must start and report the database as down.

## What gets built

### Backend (`backend/`)

- `pyproject.toml` managed by uv. Python 3.14 (see Versions).
- `app/main.py` creates the FastAPI app, mounts the API router under `/api`, serves the static frontend at `/`, and adds basic security headers (`X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, and a Content Security Policy). The policy is `default-src 'self'`, but `script-src` and `style-src` also allow `'unsafe-inline'`, because the Next.js static export puts inline scripts in its HTML. *Our call:* tighten this to build-time hashes when admin login arrives and the page starts handling secrets.
- `app/config/settings.py` reads `DATABASE_URL` from the environment with pydantic-settings. The app fails at startup with a clear message if it is missing.
- Database access uses psycopg 3 with a sync SQLAlchemy engine (`postgresql+psycopg://`). *Our call:* psycopg 3 is the driver the LangGraph Postgres checkpointer and `langchain-postgres` use later, and sync keeps this step simple.
- `app/db/session.py` holds the SQLAlchemy engine and session. `app/db/base.py` holds the declarative base.
- `app/api/health.py`: `GET /api/health`.

| Database | HTTP status | Body |
|---|---|---|
| Reachable | 200 | `{"status": "ok", "database": "ok"}` |
| Unreachable | 503 | `{"status": "degraded", "database": "down"}` |

The database check runs `SELECT 1` with a short timeout, so the page doesn't hang when Postgres is down.

- `alembic/` with a baseline migration that creates no tables. Migrations run with `alembic upgrade head` when the app container starts, before uvicorn. Compose starts `app` only after `db` passes its health check.

### Frontend (`frontend/`)

- Next.js with `output: "export"`, TypeScript strict, Tailwind and shadcn/ui set up. pnpm.
- One route, `/`: the status page. It calls `/api/health` and shows two rows, Backend and Database, each marked connected or down, plus the time it last checked and a Recheck button.
- If `/api/health` cannot be reached at all, the page shows the backend as down.
- `src/styles/tokens.css` takes its colours and type from the design doc (warm off-white background, muted blue accent, system sans and mono), so the admin UI and the docs look like one project.
- `src/lib/api.ts` is the API client used by the page.

### Packaging

- `Dockerfile`, multi-stage: a Node stage builds the static export, and a Python stage installs the backend with uv and copies the export in.
- `docker-compose.yml`:
  - `db`: the `pgvector/pgvector:pg18` image, a named volume mounted at `/var/lib/postgresql`, a `pg_isready` health check, port 5432 published to the host so tests on the host can reach it.
  - `app`: built from the Dockerfile, port 8000, `depends_on` `db` with `condition: service_healthy`, environment from `.env`.
- `.env.example` with `DATABASE_URL` and the Postgres user, password and database name. Local-only defaults are fine. `.env` is git-ignored.

### Makefile

| Target | Does |
|---|---|
| `make up` | Copies `.env.example` to `.env` if `.env` is missing, then `docker compose up --build` |
| `make down` | `docker compose down` |
| `make logs` | Follows the Compose logs |
| `make migrate` | Runs `alembic upgrade head` in the app container |
| `make test` | Backend and frontend tests (see Tests) |
| `make lint` | Ruff, mypy, ESLint, Prettier check, TypeScript check |
| `make fmt` | Ruff format and Prettier write |
| `make help` | Lists the targets (the default target) |

## Versions

Use the newest stable release of every tool, as long as it works with the others. Checked on 2026-10-17:

| Tool | Version | Note |
|---|---|---|
| Python | 3.14 | Presidio and spaCy support it. LangGraph doesn't list 3.14 yet. Check it in step 3, and drop to 3.13 only if it fails. |
| Node | 24 LTS | Node 26 is newer but isn't LTS yet. *Our call.* |
| Postgres | 18 (`pgvector/pgvector:pg18`) | Postgres 18 images store data under `/var/lib/postgresql`, so mount the volume there, not at `.../data`. |
| FastAPI, SQLAlchemy 2.1, Alembic, psycopg 3, pydantic-settings | latest | All support 3.14 |
| Next.js 16, React 19, Tailwind 4 | latest | |
| TypeScript, ESLint, Vitest, Prettier | latest major | TypeScript 7, ESLint 10 and Vitest 5 are new majors. If one breaks the Next.js build or lint, drop it back one major and note why in the plan. |
| Ruff, mypy, pytest, uv, pnpm | latest | |

The plan pins exact versions in `pyproject.toml`, `uv.lock`, `package.json` and `pnpm-lock.yaml`.

## Tests

These follow [project-structure.md](../project-structure.md#tests). There is almost no logic in this step, so there are few tests.

- **Backend integration** (`tests/integration/`), against the real Compose Postgres:
  - Health returns 200 and `database: ok` when Postgres is up.
  - Health returns 503 and `database: down` when the app points at an unreachable database.
  - The Alembic baseline upgrades and downgrades cleanly.
- **Frontend** (Vitest): the status page shows connected for an ok response, down for a 503, and backend down when the request fails. Mock `fetch` at the edge.
- Tests run on the host. `make test` starts `db` if needed, then runs `uv run pytest` and `pnpm test`. The host needs uv and pnpm for tests. `make up` only needs Docker.
- Tests use their own database, `dev_slack_bot_test`, on the same Postgres container, so they never touch dev data. `make test` creates it if it is missing, so it also works on a volume that existed before this step. Tests connect through `TEST_DATABASE_URL`, which defaults to `localhost:5432`, while the app's `DATABASE_URL` uses the Compose host `db`. *Our call.*

## Docs to update when this step is done

- `README.md`: replace "design only" with a Quick start (`make up`, then open `localhost:8000`).
- `docs/project-structure.md`: change the status note from "target layout" to say which parts now exist.

## Builder's calls

These are open. Choose and note the choice in the plan.

- How the static files are mounted in FastAPI, as long as `/api/*` is never shadowed by the frontend.
- Layout and wording of the status page, within the design doc's style.
