SHELL := /usr/bin/env bash

COMPOSE_DIR := infra/compose
COMPOSE_ENV := $(COMPOSE_DIR)/.env
COMPOSE_FILE := $(COMPOSE_DIR)/docker-compose.yml
COMPOSE := docker compose --env-file $(COMPOSE_ENV) -f $(COMPOSE_FILE)

.PHONY: bootstrap dev dev-web dev-admin dev-api dev-agent dev-worker lint typecheck test format-check check verify-scaffold ci-contracts ci-local infra-env infra-up infra-status infra-down infra-reset infra-logs doctor infra-smoke infra-persistence

bootstrap:
	corepack enable
	corepack prepare pnpm@11.4.0 --activate
	pnpm install --frozen-lockfile
	uv sync --all-packages --frozen

verify-scaffold:
	python3 scripts/verify_scaffold.py

dev:
	bash scripts/dev.sh

dev-web:
	pnpm --filter @lumi/web dev

dev-admin:
	pnpm --filter @lumi/admin dev

dev-api:
	uv run --package lumi-api lumi-api

dev-agent:
	uv run --package lumi-agent-runtime lumi-agent-smoke

dev-worker:
	uv run --package lumi-worker-media celery -A lumi_worker_media.app:celery_app worker --pool=solo --loglevel=INFO

format-check:
	pnpm format:check
	uv run ruff format --check apps services

lint:
	pnpm lint
	uv run ruff check apps services

typecheck:
	pnpm typecheck
	uv run pyright

test:
	pnpm test
	uv run pytest

check: verify-scaffold format-check lint typecheck test

ci-contracts:
	bash scripts/ci-contracts

ci-local: check ci-contracts
	pnpm build

infra-env:
	@if [ ! -f "$(COMPOSE_ENV)" ]; then \
		cp "$(COMPOSE_DIR)/env.local.example" "$(COMPOSE_ENV)"; \
		echo "Created $(COMPOSE_ENV) from LOCAL_ONLY example"; \
	fi

infra-up: infra-env
	$(COMPOSE) up -d --build --wait --wait-timeout 180 postgres redis rabbitmq minio mailpit
	$(COMPOSE) run --rm minio-init

infra-status: infra-env
	$(COMPOSE) ps

infra-down: infra-env
	$(COMPOSE) down --remove-orphans

infra-reset: infra-env
	@if [ "$(CONFIRM)" != "1" ]; then \
		echo "Refusing destructive reset. Re-run with: CONFIRM=1 make infra-reset"; \
		exit 2; \
	fi
	$(COMPOSE) down --volumes --remove-orphans

doctor: infra-env
	bash scripts/doctor

infra-smoke: infra-env
	bash scripts/infra-smoke

infra-persistence: infra-env
	bash scripts/infra-persistence

infra-logs: infra-env
	$(COMPOSE) logs --tail=200 -f
