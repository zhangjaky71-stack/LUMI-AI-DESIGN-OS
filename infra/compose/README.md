# LUMI Local Infrastructure — NODE-03

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

The Compose project uses fixed local volume names:

- `lumi_postgres_data`
- `lumi_redis_data`
- `lumi_rabbitmq_data`
- `lumi_minio_data`

Do not use `infra-reset` when you need to keep local data.

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

Each queue will gain a `<queue>.dlq` policy when routing is implemented in NODE-19. NODE-03 does not claim worker routing early.

## Windows 11

Use Docker Desktop with WSL2 integration and keep the repository in the WSL Linux filesystem (for example `~/src/LUMI-AI-DESIGN-OS`) rather than `/mnt/c` for high-I/O Node/Python work.

## Security boundary

These credentials and management ports are for localhost development only. Never reuse them in staging/production and never expose RabbitMQ/MinIO management ports publicly.

## Observability overlay

`docker-compose.observability.yml` is reserved as the local overlay contract. The production-like Prometheus/Grafana/Tempo setup is intentionally deferred to NODE-67 so NODE-03 does not freeze an observability design prematurely.
