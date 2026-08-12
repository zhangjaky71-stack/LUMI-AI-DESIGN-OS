SHELL := /usr/bin/env bash

.PHONY: bootstrap dev dev-web dev-admin dev-api dev-agent dev-worker lint typecheck test format-check check verify-scaffold

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
