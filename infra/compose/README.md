# LUMI Local Infrastructure — NODE-03 + NODE-67 Overlay

This directory provides the local, cloud-free infrastructure baseline used by later LUMI nodes.

## Services

| Service | Container DNS | Host port | Purpose |
|---|---|---:|---|
| PostgreSQL + pgvector | `postgres:5432` | 5432 | durable business data and vectors |
| Redis | `redis:6379` | 6379 | cache, rate-limit, ephemeral coordination |
| RabbitMQ | `rabbitmq:5672` | 5672 | async broker |
| RabbitMQ UI | `rabbitmq:15672` | 15672 | local management only |
| MinIO API | `minio:9000` | 9000 | S3-compatible object storage |
| MinIO console | `minio:9001` | 9001 | local management only |
| Mailpit SMTP | `mailpit:1025` | 1025 | captured test mail |
| Mailpit UI/API | `mailpit:8025` | 8025 | inspect captured mail |

Host ports can be overridden in `infra/compose/.env`.

## First start

From WSL2/Linux/macOS:

```bash
make infra-up
make doctor
```

`make infra-up` automatically copies `env.local.example` to the gitignored `.env` on first use. The example credentials are explicitly LOCAL_ONLY.

MinIO Community Edition is source-only in the current upstream distribution model. LUMI therefore builds a local container from the fixed `MINIO_RELEASE` using `infra/docker/minio/Dockerfile`; it does not depend on a disappearing pre-built MinIO registry tag.

## Daily commands

```bash
make infra-up
make infra-status
make doctor
make infra-smoke
make infra-persistence
make infra-down
```

`make infra-down` stops containers but preserves named volumes. A destructive reset requires an explicit acknowledgement:

```bash
CONFIRM=1 make infra-reset
```

## Persistent volumes

The base Compose project uses fixed local volume names:

- `lumi_postgres_data`
- `lumi_redis_data`
- `lumi_rabbitmq_data`
- `lumi_minio_data`

NODE-67 adds local observability volumes:

- `lumi_tempo_data`
- `lumi_loki_data`
- `lumi_prometheus_data`
- `lumi_grafana_data`

Do not use destructive volume cleanup when you need to retain local evidence.

## PostgreSQL bootstrap

On a fresh volume, the init script enables only infrastructure-level extensions and local roles:

- `vector`
- `pgcrypto`
- `lumi_app`
- `lumi_migration`

NODE-03 deliberately creates no business tables. NODE-10 owns the application schema and migrations.

If you change bootstrap users/passwords after PostgreSQL has already initialized, use `CONFIRM=1 make infra-reset` so the init scripts can run again.

## MinIO buckets

The one-shot `minio-init` service idempotently creates:

- `lumi-assets`
- `lumi-exports`
- `lumi-sandbox`

Application code should use keys shaped like `org/{org_id}/project/{project_id}/...` and later use presigned S3 URLs for browser uploads.

## RabbitMQ queue contract

NODE-03 prepares the broker for later declaration of:

- `lumi.media.image`
- `lumi.media.video`
- `lumi.media.export`
- `lumi.system.low`

Each queue gains its runtime/DLQ semantics in NODE-19 and later nodes.

## Observability overlay — NODE-67

`docker-compose.observability.yml` is now active and is always combined with the base Compose file. It provides local-only:

| Service | Local URL/port | Purpose |
|---|---|---|
| OpenTelemetry Collector | `127.0.0.1:4317/4318` | OTLP receive/fan-out |
| Collector health | `127.0.0.1:13133` | telemetry pipeline readiness |
| Prometheus | `http://127.0.0.1:9090` | metrics/SLO/alerts |
| Tempo | `http://127.0.0.1:3200` | distributed traces |
| Loki | `http://127.0.0.1:3100` | structured logs |
| Grafana | `http://127.0.0.1:3001` | provisioned dashboards/explore |

Start and validate:

```bash
make observability-up
make observability-smoke
make observability-status
```

Inspect or stop:

```bash
make observability-logs
make observability-down
```

`make observability-up` starts the base local dependencies first and then the telemetry overlay. `make observability-smoke` checks the merged Compose model and backend readiness endpoints. If `LUMI_API_URL` is set, it also probes the API's `/internal/metrics` endpoint.

Grafana provisions Prometheus, Tempo and Loki automatically plus the `LUMI Operational Overview` dashboard. The default local Grafana credentials are intentionally local-only and must be replaced by deployment secret/IAM controls outside local development.

The API metrics path is an internal scrape endpoint, not a public product endpoint. Staging/production ingress must keep it private.

The current repository lockfile does not contain OpenTelemetry Python SDK/exporter packages. NODE-67 therefore treats full SDK/OTLP application export as an explicit remaining integration gate instead of hand-editing `uv.lock`.

## Windows 11

Use Docker Desktop with WSL2 integration and keep the repository in the WSL Linux filesystem (for example `~/src/LUMI-AI-DESIGN-OS`) rather than `/mnt/c` for high-I/O Node/Python work.

## Security boundary

These credentials and management ports are for localhost development only. Never reuse them in staging/production and never expose RabbitMQ/MinIO/Grafana/Prometheus/Tempo/Loki/Collector management or ingestion ports directly to the public Internet.
