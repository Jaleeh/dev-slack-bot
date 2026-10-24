.DEFAULT_GOAL := help
.PHONY: help up dev db down logs migrate test lint fmt

# Make creates .env from the example first if it is missing, then re-reads it.
-include .env

# Built from .env so a changed user, password or host port reaches the tests too.
# The test suite creates this database if it is missing.
TEST_DATABASE_URL ?= postgresql+psycopg://$(POSTGRES_USER):$(POSTGRES_PASSWORD)@localhost:$(POSTGRES_HOST_PORT)/dev_slack_bot_test
export TEST_DATABASE_URL

# make dev runs the backend on this machine, so it reaches Postgres through the published port.
DEV_DATABASE_URL := postgresql+psycopg://$(POSTGRES_USER):$(POSTGRES_PASSWORD)@localhost:$(POSTGRES_HOST_PORT)/$(POSTGRES_DB)

help: ## List the available targets
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(firstword $(MAKEFILE_LIST)) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-10s %s\n", $$1, $$2}'

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

lint: ## Run linters, type checks and format checks
	cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy
	cd frontend && pnpm lint && pnpm typecheck && pnpm format:check

fmt: ## Format backend and frontend code
	cd backend && uv run ruff format .
	cd frontend && pnpm format
