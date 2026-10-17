# Step 1: Skeleton Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `make up` starts FastAPI, the static Next.js admin UI and Postgres locally, and a status page shows whether the backend and the database are connected.

**Architecture:** One app image: a Node stage builds the Next.js static export and a Python stage serves it from FastAPI next to `/api`. Postgres with pgvector runs as a second Compose service. A Makefile wraps every dev command. Tests run on the host against the Compose Postgres, using a separate test database.

**Tech Stack:** Python 3.14, uv, FastAPI, SQLAlchemy 2.1 (sync, psycopg 3), Alembic, pydantic-settings, pytest, Ruff, mypy · Node 24 LTS, pnpm, Next.js 16, React 19, Tailwind 4, shadcn/ui, Vitest, Testing Library, ESLint, Prettier · Postgres 18 (`pgvector/pgvector:pg18`), Docker Compose, Make.

**Spec:** [`docs/specs/2026-10-17-step-1-skeleton.md`](../specs/2026-10-17-step-1-skeleton.md)

## Global Constraints

- Newest stable version of every tool that works with the rest. If TypeScript 7, ESLint 10 or Vitest 5 breaks the build or lint, drop that tool back one major version and record why in this plan.
- Python 3.14. Node 24 LTS. Postgres image `pgvector/pgvector:pg18`, volume mounted at `/var/lib/postgresql`.
- Database URLs use `postgresql+psycopg://`. Sync SQLAlchemy engine.
- `DATABASE_URL` is required. The app fails at startup with a clear message if it is missing.
- Tests never touch the dev database. They use `dev_slack_bot_test` through `TEST_DATABASE_URL`.
- No CI, no GitHub remote, no pushing. Local git only. **Commit only when the user says so.** The commit steps below are there for when they do.
- Don't create feature folders (`agent/`, `retrieval/`, `privacy/`, `repos/`, `chat/`, `providers/`). Later steps create them.
- Follow the import direction in `docs/project-structure.md`: `api/` → `db/`, `config/`. Never the other way.

## Review Focus

1. **Postgres hangs instead of refusing.** Health must return 503 within the timeout, not hang the page. Tested in Task 2 with a non-routable host.
2. **Unknown `/api/*` path.** It must return a JSON 404, not the frontend's `index.html`. Tested in Task 4.
3. **`DATABASE_URL` missing.** Startup must fail with an error that names the setting. Tested in Task 2.
4. **Database volume created before the test database existed.** `make test` must still find `dev_slack_bot_test`. It creates it if missing (Task 6). Verified in Task 6's manual check.
5. **Host port 5432 already used by a local Postgres.** `POSTGRES_HOST_PORT` in `.env` moves it (Task 1). `TEST_DATABASE_URL` must use the same port.

---

### Task 1: Repo basics and Postgres

**Files:**
- Create: `.gitignore`, `.env.example`, `docker-compose.yml` (the `db` service only), `Makefile` (`help`, `db`, `down`, `logs`)

**Interfaces:**
- Produces: Compose service `db`. Env names `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `POSTGRES_HOST_PORT`, `DATABASE_URL`, `TEST_DATABASE_URL`. Make targets `help` (default), `db`, `down`, `logs`.

- [ ] **Step 1: Write `.gitignore`.** Include `.DS_Store`, `.env`, `.venv/`, `__pycache__/`, `.mypy_cache/`, `.ruff_cache/`, `.pytest_cache/`, `node_modules/`, `frontend/out/`, `frontend/.next/`.
- [ ] **Step 2: Write `.env.example`** with these local-only values:

```dotenv
POSTGRES_USER=devbot
POSTGRES_PASSWORD=devbot
POSTGRES_DB=dev_slack_bot
POSTGRES_HOST_PORT=5432
DATABASE_URL=postgresql+psycopg://devbot:devbot@db:5432/dev_slack_bot
TEST_DATABASE_URL=postgresql+psycopg://devbot:devbot@localhost:5432/dev_slack_bot_test
```

- [ ] **Step 3: Write the `db` service.** Use `pgvector/pgvector:pg18`, take `env_file: .env`, publish `${POSTGRES_HOST_PORT:-5432}:5432`, mount named volume `pgdata` at `/var/lib/postgresql`, and add a `pg_isready -U $${POSTGRES_USER} -d $${POSTGRES_DB}` healthcheck (interval 2s, retries 15).
- [ ] **Step 4: Write the Makefile.** `help` lists the targets from `## ` comments. `db` copies `.env.example` to `.env` if `.env` is missing, then runs `docker compose up -d --wait db`.
- [ ] **Step 5: Verify.** Run `make db && docker compose exec db psql -U devbot -d dev_slack_bot -c "select 1"`. Expected: one row with `1`. Then run `make down`.
- [ ] **Step 6: Commit (only when the user says so).** Message: `chore: add postgres service, env example and makefile`.

### Task 2: Backend app, settings and health route

**Files:**
- Create: `backend/pyproject.toml`, `backend/app/__init__.py`, `backend/app/main.py`, `backend/app/config/__init__.py`, `backend/app/config/settings.py`, `backend/app/db/__init__.py`, `backend/app/db/base.py`, `backend/app/db/session.py`, `backend/app/api/__init__.py`, `backend/app/api/health.py`
- Test: `backend/tests/conftest.py`, `backend/tests/integration/test_health.py`, `backend/tests/unit/test_settings.py`

**Interfaces:**
- Consumes: the `db` service and `TEST_DATABASE_URL` from Task 1.
- Produces:
  - `app.config.settings.Settings(BaseSettings)` with fields `database_url: str` (required) and `frontend_dir: Path = Path("static")`. `get_settings() -> Settings` is cached.
  - `app.db.session.make_engine(database_url: str) -> Engine`. It sets `connect_args={"connect_timeout": DB_CONNECT_TIMEOUT_SECONDS}` with the constant set to `2`. `get_engine() -> Engine` is cached and built from `get_settings()`.
  - `app.db.base.Base` (`DeclarativeBase`).
  - `app.api.health.router`: `GET /health`, with the engine injected through `Depends(get_engine)`.
  - `app.main.create_app(settings: Settings) -> FastAPI` mounts the router under `/api`. Module-level `app = create_app(get_settings())`.
  - Test fixtures:
    - `test_database_url: str` reads `TEST_DATABASE_URL`. It defaults to the value in `.env.example`.
    - `client: TestClient` uses `create_app` with `frontend_dir=tmp_path` and overrides `get_engine` with `make_engine(test_database_url)`.
    - `client_with_engine(url: str) -> TestClient` is a factory built the same way, for a given URL.

- [ ] **Step 1: Set up the project.** Run `uv init --app --python 3.14` in `backend/`. Add runtime packages: `fastapi`, `uvicorn[standard]`, `sqlalchemy`, `psycopg[binary]`, `alembic`, `pydantic-settings`. Add dev packages: `pytest`, `httpx`, `ruff`, `mypy`. Configure mypy `strict = true` and Ruff with rule sets `E,F,I,B,UP,SIM`.
- [ ] **Step 2: Write the failing tests.**

```python
# tests/integration/test_health.py
def test_health_reports_database_ok_when_postgres_is_up(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}

def test_health_reports_database_down_when_unreachable(client_with_engine):
    client = client_with_engine("postgresql+psycopg://x:y@localhost:1/none")
    response = client.get("/api/health")
    assert response.status_code == 503
    assert response.json() == {"status": "degraded", "database": "down"}

def test_health_returns_quickly_when_database_host_hangs(client_with_engine):
    client = client_with_engine("postgresql+psycopg://x:y@10.255.255.1:5432/none")
    started = time.monotonic()
    response = client.get("/api/health")
    assert response.status_code == 503
    assert time.monotonic() - started < 5

# tests/unit/test_settings.py
def test_startup_fails_naming_database_url_when_missing(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValidationError, match="database_url"):
        Settings(_env_file=None)
```

- [ ] **Step 3: Run and confirm the tests fail.** Run `make db && cd backend && uv run pytest -v`. Expected: an import error for `app.main` or `app.config.settings`. If the test database doesn't exist yet, create it now with `docker compose exec db createdb -U devbot dev_slack_bot_test`. Task 6 automates this.
- [ ] **Step 4: Implement the interfaces above.** The health route runs `SELECT 1` and catches `sqlalchemy.exc.OperationalError` only. On that error it logs a warning with the error class name, never the URL, and returns 503 via `JSONResponse`.
- [ ] **Step 5: Run and confirm the tests pass.** Run `cd backend && uv run pytest -v && uv run ruff check . && uv run mypy app`. Expected: all pass, no lint or type errors.
- [ ] **Step 6: Commit (only when the user says so).** Message: `feat: add fastapi app with database health route`.

### Task 3: Alembic baseline

**Files:**
- Create: `backend/alembic.ini`, `backend/alembic/env.py`, `backend/alembic/script.py.mako`, `backend/alembic/versions/0001_baseline.py`
- Test: `backend/tests/integration/test_migrations.py`

**Interfaces:**
- Consumes: `get_settings()` and `Base` from Task 2, and the `test_database_url` fixture.
- Produces: revision `0001_baseline` with no operations. `env.py` uses `config.get_main_option("sqlalchemy.url")` if set, otherwise `get_settings().database_url`, and `target_metadata = Base.metadata`.

- [ ] **Step 1: Write the failing test.**

```python
def test_baseline_upgrades_and_downgrades_cleanly(test_database_url):
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", test_database_url)

    command.upgrade(config, "head")
    assert current_revision(test_database_url) == "0001_baseline"

    command.downgrade(config, "base")
    assert current_revision(test_database_url) is None
```

`current_revision` is a small test helper using `MigrationContext.configure(conn).get_current_revision()`.

- [ ] **Step 2: Run and confirm the test fails.** Run `cd backend && uv run pytest tests/integration/test_migrations.py -v`. Expected: FAIL, because `alembic.ini` isn't found.
- [ ] **Step 3: Set up Alembic.** Run `uv run alembic init alembic`, edit `env.py` as described in Interfaces, and create `0001_baseline.py` with `revision = "0001_baseline"` and empty `upgrade`/`downgrade`.
- [ ] **Step 4: Run and confirm the test passes.** Run `cd backend && uv run pytest -v`. Expected: all pass.
- [ ] **Step 5: Commit (only when the user says so).** Message: `feat: add alembic baseline migration`.

### Task 4: Static frontend serving and security headers

**Files:**
- Modify: `backend/app/main.py`
- Test: `backend/tests/integration/test_app.py`

**Interfaces:**
- Consumes: `create_app(settings)` and the `client` fixture from Task 2.
- Produces: `/` serves `settings.frontend_dir/index.html`. Every response carries the security headers. If `frontend_dir` doesn't exist, the app still starts, logs a warning and serves only `/api`.

- [ ] **Step 1: Write the failing tests.** Each test writes `index.html` containing `<h1>status</h1>` into `tmp_path`.

```python
def test_root_serves_the_frontend_index(client): ...  # GET / -> 200, body contains "<h1>status</h1>"

def test_unknown_api_path_returns_json_404_not_the_frontend(client):
    response = client.get("/api/does-not-exist")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")

def test_responses_carry_security_headers(client):
    headers = client.get("/api/health").headers
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["x-frame-options"] == "DENY"
    assert headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert headers["content-security-policy"] == CSP
```

Use this exact value for `CSP`:
`default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'`

- [ ] **Step 2: Run and confirm the tests fail.** Run `cd backend && uv run pytest tests/integration/test_app.py -v`. Expected: FAIL. `/` returns 404 and the headers are missing.
- [ ] **Step 3: Implement.** Add one HTTP middleware that sets the four headers, using a module constant `SECURITY_HEADERS: Mapping[str, str]`. Include the `/api` router and a catch-all `/api/{path:path}` route that returns a JSON 404. Then mount `StaticFiles(directory=settings.frontend_dir, html=True)` at `/`. Mounting it last stops `/api/*` from ever falling through to it.
- [ ] **Step 4: Run and confirm the tests pass.** Run `cd backend && uv run pytest -v && uv run ruff check . && uv run mypy app`. Expected: all pass.
- [ ] **Step 5: Commit (only when the user says so).** Message: `feat: serve static frontend with security headers`.

### Task 5: Status page

**Files:**
- Create: `frontend/` (Next.js app), `frontend/next.config.ts`, `frontend/src/styles/tokens.css`, `frontend/src/lib/api.ts`, `frontend/src/components/status/StatusPanel.tsx`, `frontend/src/app/page.tsx`, `frontend/src/app/layout.tsx`, `frontend/vitest.config.ts`
- Test: `frontend/src/components/status/StatusPanel.test.tsx`

**Interfaces:**
- Consumes: `GET /api/health` responses as defined in the spec.
- Produces:
  - `type ConnectionState = "connected" | "down" | "unknown"`
  - `type HealthStatus = { backend: ConnectionState; database: ConnectionState; checkedAt: Date }`
  - `fetchHealth(): Promise<HealthStatus>` in `src/lib/api.ts`. A 200 gives backend and database connected. A 503 gives backend connected and database down. Any other status, or a fetch that throws, gives backend down and database unknown. It never throws.
  - `<StatusPanel />`, a client component. It checks on mount, has a "Recheck" button, and shows a row each for "Backend" and "Database" plus the last checked time.

- [ ] **Step 1: Scaffold.** Run `pnpm create next-app@latest frontend --ts --tailwind --eslint --app --src-dir --use-pnpm --import-alias "@/*"`. Set `output: "export"` in `next.config.ts`, then run `pnpm dlx shadcn@latest init` and add `button`. Add Prettier, Vitest, jsdom, `@testing-library/react`, `@testing-library/user-event`, `@testing-library/jest-dom` and `@vitejs/plugin-react`. Add scripts `test` (`vitest run`), `typecheck` (`tsc --noEmit`) and `format:check`.
- [ ] **Step 2: Write the failing tests.** `stubFetch(status, body)` is a test helper that stubs `global.fetch` with `vi.stubGlobal`.

```tsx
it("shows backend and database connected when health is ok", async () => {
  stubFetch(200, { status: "ok", database: "ok" });
  render(<StatusPanel />);
  expect(await screen.findByRole("row", { name: /backend.*connected/i })).toBeInTheDocument();
  expect(screen.getByRole("row", { name: /database.*connected/i })).toBeInTheDocument();
});

it("shows the database down when health returns 503", async () => {
  stubFetch(503, { status: "degraded", database: "down" });
  render(<StatusPanel />);
  expect(await screen.findByRole("row", { name: /database.*down/i })).toBeInTheDocument();
  expect(screen.getByRole("row", { name: /backend.*connected/i })).toBeInTheDocument();
});

it("shows the backend down when the request fails", async () => {
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
  render(<StatusPanel />);
  expect(await screen.findByRole("row", { name: /backend.*down/i })).toBeInTheDocument();
});

it("checks again when Recheck is pressed", async () => {
  stubFetch(503, { status: "degraded", database: "down" });
  render(<StatusPanel />);
  await screen.findByRole("row", { name: /database.*down/i });
  stubFetch(200, { status: "ok", database: "ok" });
  await userEvent.click(screen.getByRole("button", { name: /recheck/i }));
  expect(await screen.findByRole("row", { name: /database.*connected/i })).toBeInTheDocument();
});
```

- [ ] **Step 3: Run and confirm the tests fail.** Run `cd frontend && pnpm test`. Expected: FAIL, because `StatusPanel` isn't found.
- [ ] **Step 4: Implement `fetchHealth`, `StatusPanel` and the page.** Render the rows as a `<table>` so the row roles hold. Take the tokens in `tokens.css` from `design-doc.html`'s `:root` (`--bg #fbfaf7`, `--fg #1c1c1c`, `--muted #6a6a6a`, `--rule #e3e0d8`, `--accent #2a5f7f`, `--accent-soft #e8f0f4`, `--code-bg #f2f0e9`, `--badge-green-*`, `--badge-amber-*`) and use them for Tailwind theme colours. Show the state as a badge: green for connected, amber for down, muted for unknown. Use the system sans and mono stacks as in the design doc. Don't add web fonts.
- [ ] **Step 5: Run and confirm the tests, lint and build pass.** Run `cd frontend && pnpm test && pnpm lint && pnpm typecheck && pnpm format:check && pnpm build`. Expected: all pass, and `out/index.html` exists. If TypeScript 7, ESLint 10 or Vitest 5 breaks this, drop that tool back one major version and note it under Global Constraints.
- [ ] **Step 6: Commit (only when the user says so).** Message: `feat: add status page`.

### Task 6: App image, full Compose stack and Makefile

**Files:**
- Create: `Dockerfile`, `.dockerignore`, `backend/docker-entrypoint.sh`
- Modify: `docker-compose.yml` (add `app`), `Makefile` (add `up`, `migrate`, `test-db`, `test`, `lint`, `fmt`)

**Interfaces:**
- Consumes: everything above.
- Produces: the full set of `make` targets from the spec's Makefile table.

- [ ] **Step 1: Write the Dockerfile.** Use two stages.
  - **Stage 1:** `node:24-slim`. Run `corepack enable`, then `pnpm install --frozen-lockfile` and `pnpm build`.
  - **Stage 2:** `python:3.14-slim`. Copy `uv` from `ghcr.io/astral-sh/uv`, then run `uv sync --frozen --no-dev`. Copy `app/`, `alembic/`, `alembic.ini` and the entrypoint. Copy `frontend/out` to `/app/static`. Set `FRONTEND_DIR=/app/static`, run as a non-root user and expose port 8000.
- [ ] **Step 2: Write the entrypoint.** `docker-entrypoint.sh` runs `set -e`, then `alembic upgrade head`, then `exec uvicorn app.main:app --host 0.0.0.0 --port 8000`.
- [ ] **Step 3: Add the `app` service and the remaining Make targets.**
  - **`app` service:** `build: .`, `env_file: .env`, `ports: ["8000:8000"]`, `depends_on: {db: {condition: service_healthy}}`.
  - **Make targets:**
    - `up`: ensures `.env` exists, then runs `docker compose up --build`.
    - `migrate`: `docker compose exec app alembic upgrade head`.
    - `test-db`: creates `dev_slack_bot_test` only if `psql -tAc "select 1 from pg_database where datname='dev_slack_bot_test'"` returns nothing.
    - `test`: runs `db`, then `test-db`, then `uv run pytest` and `pnpm test`.
    - `lint`: Ruff check, Ruff format check, mypy, `pnpm lint`, `pnpm typecheck` and `pnpm format:check`.
    - `fmt`: `ruff format` and `prettier --write`.
- [ ] **Step 4: Verify each success criterion from the spec by hand.**
  1. Run `make down && docker volume rm dev-slack-bot_pgdata; make up`. Expected: the stack starts and the logs show `Running upgrade -> 0001_baseline`.
  2. Open `http://localhost:8000`. Expected: Backend and Database both show connected.
  3. Run `docker compose stop db`, then press Recheck. Expected: Database shows down within about 3 seconds. Run `docker compose start db` and press Recheck. Expected: both show connected.
  4. Run `make test && make lint`. Expected: all pass. Run `make test` a second time. Expected: it passes again, because `test-db` is idempotent.
  5. Run `curl -s localhost:8000/api/nope -i | head -1`. Expected: `HTTP/1.1 404`.
- [ ] **Step 5: Commit (only when the user says so).** Message: `feat: add app image, compose stack and make targets`.

### Task 7: Docs

**Files:**
- Modify: `README.md`, `docs/project-structure.md`

- [ ] **Step 1: README.** Replace the "design only" status line with: Step 1 (skeleton) is built. Add a **Quick start** section with three lines: install Docker and Make, run `make up`, open `http://localhost:8000`. Then add one line saying tests and lint need uv and pnpm on the host (`make test`, `make lint`).
- [ ] **Step 2: project-structure.md.** Replace the "target layout" status note with: built so far are `backend/app/{main.py,api,config,db}`, `backend/alembic`, `backend/tests/{unit,integration}`, `frontend/`, `Dockerfile`, `docker-compose.yml` and `Makefile`. The rest is created in the step that needs it.
- [ ] **Step 3: Commit (only when the user says so).** Message: `docs: add quick start and update structure status`.
