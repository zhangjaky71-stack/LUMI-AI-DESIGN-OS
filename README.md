# LUMI AI Design OS

LUMI is a document-driven, production-oriented AI Design Operating System built on the Architecture V2 baseline. This repository grows node-by-node according to [`docs/NODE-INDEX.md`](docs/NODE-INDEX.md).

## Development baseline

- Node.js 24 LTS
- pnpm 11
- Python 3.12
- uv workspace
- Next.js App Router + React
- FastAPI
- LangGraph + LangChain + Deep Agents
- Celery media worker

## Windows 11

Use **WSL2 + Docker Desktop**. Keep the repository inside the Linux filesystem (for example `~/code/LUMI-AI-DESIGN-OS`) rather than under `/mnt/c` for better file-system performance.

## Bootstrap

Install Node 24 LTS, enable Corepack, install uv, then:

```bash
cp .env.example .env
make bootstrap
```

NODE-03 will add Docker Compose infrastructure. Until then the API health endpoints, Agent import smoke and worker in-memory health task do not require commercial API keys.

## Run

```bash
make dev-web       # http://localhost:3000
make dev-admin     # http://localhost:3001
make dev-api       # http://localhost:8000
make dev-agent     # import-only Agent runtime smoke
make dev-worker    # media worker; NODE-03 supplies RabbitMQ
```

Or run Web + API together with `make dev`.

## Health endpoints

| Component | Endpoint / command |
|---|---|
| Web | `http://localhost:3000/health` |
| API live | `GET http://localhost:8000/health/live` |
| API ready | `GET http://localhost:8000/health/ready` |
| API version | `GET http://localhost:8000/version` |
| Agent Runtime | `make dev-agent` |
| Media Worker | `health.ping` task / `make dev-worker` |

## Quality gate

```bash
make check
```

The Node and Python dependency graphs are committed as `pnpm-lock.yaml` and `uv.lock`. CI and production installs use frozen lockfiles.

## Secrets

Never commit `.env`, API keys, access tokens, cloud credentials or customer data. `.env.example` contains local-only placeholders. Browser-visible variables must be explicitly prefixed with `NEXT_PUBLIC_` and must never contain server secrets.

## Architecture and execution

- [`docs/NODE-INDEX.md`](docs/NODE-INDEX.md) — implementation order and status.
- [`docs/IMPLEMENTATION-PROTOCOL.md`](docs/IMPLEMENTATION-PROTOCOL.md) — Definition of Complete.
- [`docs/01-ARCHITECTURE-V2-FREEZE.md`](docs/01-ARCHITECTURE-V2-FREEZE.md) — frozen architecture boundaries.
