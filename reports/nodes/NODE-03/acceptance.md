# NODE-03 Acceptance Report

> Status: **COMPLETE**  
> Node: **NODE-03 — Local Infrastructure**  
> Implemented Commit: `4f25b590a1bc643e2925551ce48c6d840c15842d`  
> Validated Workflow: `NODE-03 Local Infrastructure` / Run `31585919646` / Job `94079599321`  
> Validated At: `2026-08-12`  
> Workflow URL: `https://github.com/zhangjaky71-stack/LUMI-AI-DESIGN-OS/actions/runs/31585919646`

---

## 1. Result

NODE-03 is accepted as the local infrastructure baseline for LUMI AI Design OS.

The final GitHub Actions run started the stack from a clean hosted Docker runner, waited for all long-running services to become healthy, executed the human-readable doctor, exercised real object-storage and SMTP round trips, verified restart persistence, and proved both the safe stop path and the explicit destructive-reset guard.

## 2. Delivered infrastructure

- PostgreSQL 17 with pgvector and `pgcrypto`.
- Local PostgreSQL roles `lumi_app` and `lumi_migration`, with no NODE-10 business schema created early.
- Redis 7.4 with password protection and AOF persistence.
- RabbitMQ 4.1 management image with AMQP and local management API.
- MinIO Community Edition built locally from the fixed upstream release `RELEASE.2025-10-15T17-29-55Z`.
- Idempotent MinIO bootstrap for `lumi-assets`, `lumi-exports`, and `lumi-sandbox`.
- Mailpit SMTP capture plus HTTP inspection endpoint.
- Fixed local Docker network and named persistent volumes.
- Gitignored local Compose environment with explicitly LOCAL_ONLY credentials.
- `make infra-up`, `infra-status`, `infra-down`, `infra-reset`, `infra-logs`, `doctor`, `infra-smoke`, and `infra-persistence`.
- Windows 11 / WSL2 local runbook.
- Independent NODE-03 GitHub Actions infrastructure acceptance workflow.

## 3. Acceptance evidence

| Gate | Result |
|---|---|
| Docker / Compose available | PASS |
| Compose model validation | PASS |
| Clean `make infra-up` | PASS |
| PostgreSQL healthy | PASS |
| Redis healthy | PASS |
| RabbitMQ healthy | PASS |
| MinIO healthy | PASS |
| Mailpit healthy | PASS |
| PostgreSQL `SELECT 1` | PASS |
| pgvector extension | PASS |
| local DB roles | PASS |
| Redis PING | PASS |
| RabbitMQ broker diagnostics | PASS |
| RabbitMQ management HTTP API | PASS |
| MinIO bucket bootstrap | PASS |
| MinIO PUT/GET round trip | PASS |
| Mailpit SMTP receive + API lookup | PASS |
| PostgreSQL restart persistence | PASS |
| MinIO restart persistence | PASS |
| unconfirmed destructive reset refused | PASS |
| safe `make infra-down` preserves volumes | PASS |
| confirmed destructive reset | PASS |

## 4. Key validation excerpts

The final run reported:

```text
Doctor result: PASS
Infrastructure smoke: PASS
PASS  MinIO PUT/GET round trip
PASS  Mailpit SMTP receive + API lookup
PASS  PostgreSQL data survived restart
PASS  MinIO object survived restart
destructive reset correctly refused
```

All five long-running services were reported as `healthy` before doctor and smoke execution.

## 5. Implementation notes

### MinIO distribution

Current MinIO Community Edition is built by LUMI from a fixed upstream source release because the current community distribution is source-oriented rather than relying on an unstable/missing prebuilt registry tag. The Docker build is reproducible from `infra/docker/minio/Dockerfile` and the pinned `MINIO_RELEASE` value.

### RabbitMQ readiness

The management check uses authenticated `GET /api/overview`, matching the RabbitMQ 4.1 HTTP API. Broker readiness is independently checked through `rabbitmq-diagnostics -q ping`.

### Scope discipline

NODE-03 intentionally does not create application business tables, worker queues/routing, cloud buckets, production secrets, or production observability. Those remain owned by their later nodes.

## 6. Non-blocking warnings

- GitHub Actions currently emits a platform warning that `actions/checkout@v4` targets a deprecated Node.js action runtime and is forced onto Node 24 by the hosted runner. This is external to the LUMI application containers and did not affect NODE-03 acceptance.
- Cold CI builds compile the fixed MinIO source release and are therefore slower than pulling a prebuilt image. Local developer rebuilds can reuse Docker layer/image cache; CI caching optimization belongs in NODE-04.

## 7. Verdict

**PASS — NODE-03 COMPLETE.**

Next node: **NODE-04 — CI Foundation**.
