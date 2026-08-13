SHELL := /usr/bin/env bash

COMPOSE_DIR := infra/compose
COMPOSE_ENV := $(COMPOSE_DIR)/.env
COMPOSE_FILE := $(COMPOSE_DIR)/docker-compose.yml
COMPOSE := docker compose --env-file $(COMPOSE_ENV) -f $(COMPOSE_FILE)

.PHONY: bootstrap dev dev-web dev-admin dev-api dev-agent dev-worker lint typecheck test format-check check verify-scaffold ci-contracts ci-local eval-smoke eval eval-live eval-report product-parity-validate model-provider-validate model-gateway-contract sandbox-contract sandbox-e2e infra-env infra-up infra-status infra-down infra-reset infra-logs doctor infra-smoke infra-persistence db-upgrade db-downgrade-one db-current db-seed

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
	uv run ruff format --check apps services evals

lint:
	pnpm lint
	uv run ruff check apps services evals

typecheck:
	pnpm typecheck
	uv run pyright

test:
	pnpm test
	uv run pytest

check: verify-scaffold format-check lint typecheck test

product-parity-validate:
	python3 scripts/validate_product_parity.py

model-provider-validate:
	python3 scripts/validate_model_provider_matrix.py

model-gateway-contract:
	PYTHONPATH=services/model-gateway/src python3 scripts/validate_model_gateway_contract.py
	PYTHONPATH=services/model-gateway/src python3 -m unittest discover -s services/model-gateway/tests -p 'test_*.py'
	PYTHONPATH=services/model-gateway/src python3 scripts/integration_model_gateway.py

sandbox-contract:
	PYTHONPATH=services/sandbox-runtime/src python3 scripts/validate_sandbox_runtime_contract.py
	PYTHONPATH=services/sandbox-runtime/src python3 -m unittest discover -s services/sandbox-runtime/tests -p 'test_*.py'

sandbox-e2e:
	docker build -t lumi-sandbox:node21-v1 -f infra/sandbox/Dockerfile infra/sandbox
	LUMI_SANDBOX_DOCKER_E2E=1 PYTHONPATH=services/sandbox-runtime/src python3 scripts/integration_sandbox_runtime.py

ci-contracts:
	bash scripts/ci-contracts

eval-smoke:
	rm -f evals/reports/*.json evals/reports/*.md
	uv run python -m evals.cli compare --suite smoke --out evals/reports

eval:
	@test -n "$(SUITE)" || (echo "SUITE is required, e.g. make eval SUITE=smoke" >&2; exit 2)
	uv run python -m evals.cli run --suite "$(SUITE)" --out evals/reports

eval-live:
	@test -n "$(SUITE)" || (echo "SUITE is required, e.g. make eval-live SUITE=image" >&2; exit 2)
	uv run python -m evals.cli live --suite "$(SUITE)"

eval-report:
	@test -n "$(RUN_ID)" || (echo "RUN_ID must be a JSON report path" >&2; exit 2)
	uv run python -m evals.cli report --run "$(RUN_ID)"

ci-local: check ci-contracts eval-smoke
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
		echo "Refusing destructive reset. Re-run with: CONFIRM=1 make infra-reset" >&2; \
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

db-upgrade: infra-env
	bash scripts/db-local upgrade

db-downgrade-one: infra-env
	bash scripts/db-local downgrade-one

db-current: infra-env
	bash scripts/db-local current

db-seed: infra-env
	bash scripts/db-local seed
