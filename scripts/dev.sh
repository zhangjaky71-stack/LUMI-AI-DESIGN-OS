#!/usr/bin/env bash
set -euo pipefail
trap 'kill 0' EXIT INT TERM

pnpm --filter @lumi/web dev &
uv run --package lumi-api lumi-api &
wait
