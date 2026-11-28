# Everyday commands. `make help` lists them.
#
# Backend commands read .env through uv; nothing here needs variables exported in the shell.
# pnpm runs through corepack so the version pinned in web/package.json is the one used.

UV   := cd backend && uv run --env-file ../.env
PNPM ?= cd web && corepack pnpm
COMPOSE := docker compose --env-file .env -f infra/docker-compose.dev.yml

.DEFAULT_GOAL := help
.PHONY: help setup db-up db-down db-bootstrap migrate user run worker beat web test lint \
        typecheck api-types check hygiene image

help: ## List the commands
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F ':.*## ' '{printf "  %-14s %s\n", $$1, $$2}'

setup: ## One-time setup: git hooks, .env, dependencies
	./scripts/setup-dev.sh
	test -f .env || cp .env.example .env
	cd backend && uv sync
	$(PNPM) install

db-up: ## Start the local Postgres and Redis (roles and extensions are created on first start)
	$(COMPOSE) up -d --wait

db-down: ## Stop the local Postgres and Redis (data is kept)
	$(COMPOSE) down

db-bootstrap: ## Re-run the role bootstrap against the running local Postgres
	$(COMPOSE) exec -T postgres bash -s < infra/postgres/bootstrap.sh

migrate: ## Apply migrations as the schema owner
	$(UV) sh -c 'DATABASE_URL="$$MIGRATOR_DATABASE_URL" SERVICE_NAME=migrate python manage.py migrate'

user: ## Create a user: make user EMAIL=someone@example.org ROLE=member
	$(UV) python manage.py create_user $(EMAIL) --role $(or $(ROLE),member)

run: ## Run the API on :8000 (as the app role)
	$(UV) python manage.py runserver 127.0.0.1:8000

worker: ## Run the Celery worker (as the app role)
	$(UV) sh -c 'SERVICE_NAME=worker celery -A config worker --loglevel=INFO --concurrency=2'

beat: ## Run the Celery scheduler (exactly one may run)
	$(UV) sh -c 'SERVICE_NAME=beat celery -A config beat --loglevel=INFO --schedule celerybeat-schedule'

web: ## Run the web client on :5173, proxying /api to :8000
	$(PNPM) dev

test: ## Run both test suites
	$(UV) pytest
	$(PNPM) test

lint: ## Lint and format-check both codebases
	$(UV) ruff check .
	$(UV) ruff format --check .
	$(PNPM) lint

typecheck: ## Type-check both codebases
	$(UV) mypy .
	$(PNPM) typecheck

api-types: ## Regenerate the web client's types from the API schema
	cd backend && uv run python manage.py export_openapi_schema --settings config.settings_test \
		--api config.api.api --indent 2 --sorted --output ../web/openapi.json
	$(PNPM) gen:api

check: lint typecheck test ## Everything CI runs, plus a check that the API types are current
	$(MAKE) api-types
	git diff --exit-code -- web/openapi.json web/src/api/schema.d.ts
	$(PNPM) build

hygiene: ## Scan the full git history for personal data, stray documents and personal emails
	python3 scripts/hygiene.py history --require-denylist

image: ## Build the production image
	docker build -f infra/Dockerfile -t job-seeker:local .
