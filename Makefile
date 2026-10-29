.DEFAULT_GOAL := help
.PHONY: help up dev db down logs migrate test test-models lint fmt eval eval-answers ask eval-agent regrade

# Make creates .env from the example first if it is missing, then re-reads it.
-include .env

# Built from .env so a changed user, password or host port reaches the tests too.
# The test suite creates this database if it is missing.
TEST_DATABASE_URL ?= postgresql+psycopg://$(POSTGRES_USER):$(POSTGRES_PASSWORD)@localhost:$(POSTGRES_HOST_PORT)/dev_slack_bot_test
export TEST_DATABASE_URL

# make dev runs the backend on this machine, so it reaches Postgres through the published port.
DEV_DATABASE_URL := postgresql+psycopg://$(POSTGRES_USER):$(POSTGRES_PASSWORD)@localhost:$(POSTGRES_HOST_PORT)/$(POSTGRES_DB)

help: ## List the available targets
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(firstword $(MAKEFILE_LIST)) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-13s %s\n", $$1, $$2}'

.env:
	cp .env.example .env

up: ## Build and start the whole stack (app on http://localhost:8000)
	docker compose up --build

dev: db ## Run backend and frontend on this machine with hot reload (http://localhost:3000)
	docker compose stop app
	(cd backend && DATABASE_URL=$(DEV_DATABASE_URL) uv run alembic upgrade head && \
		DATABASE_URL=$(DEV_DATABASE_URL) uv run uvicorn app.main:app_factory --factory --reload --port 8000) & \
	(cd frontend && pnpm dev) & \
	wait

db: ## Start Postgres in the background and wait until it is healthy
	docker compose up -d --wait db

down: ## Stop the stack
	docker compose down

logs: ## Follow the stack logs
	docker compose logs -f

migrate: ## Run database migrations in the running app container
	docker compose exec app alembic upgrade head

test: db ## Run backend and frontend tests (needs uv and pnpm on the host)
	cd backend && uv run pytest
	cd frontend && pnpm test

test-models: ## Run the learning tests that call real models (needs Ollama; about 2 min)
	cd backend && uv run pytest -m model

lint: ## Run linters, type checks and format checks
	cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy
	cd frontend && pnpm lint && pnpm typecheck && pnpm format:check

fmt: ## Format backend and frontend code
	cd backend && uv run ruff format .
	cd frontend && pnpm format

eval: ## Score retrieval and PII redaction on the eval sets (fetches the sample repo on first run)
	cd backend && uv run python -m evals.runner

eval-answers: ## Grade the planted answers with the local model (needs Ollama running)
	cd backend && uv run python -m evals.answer_runner

# Passed through the environment, so quotes and apostrophes in the question survive.
export Q

ask: ## Answer Q="..." about the sample repo with the local agent (needs Ollama; takes minutes)
	cd backend && uv run python -m evals.ask

# Passed through the environment, so the space-separated list reaches the runner whole.
export IDS

eval-agent: ## Run the agent on every question, or IDS="a b" (needs Ollama; a full run takes hours)
	cd backend && uv run python -m evals.agent_runner

# RUN is given from the repo root, so it is made absolute before the cd.
regrade: ## Re-judge a saved eval-agent run REPS times (default 5): RUN=path (needs Ollama)
	cd backend && RUN="$(abspath $(RUN))" REPS="$(REPS)" uv run python -m evals.regrade
