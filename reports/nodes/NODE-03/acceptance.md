# NODE-03 Acceptance Report

> Status: **VALIDATING**  
> Node: **NODE-03 — Local Infrastructure**  
> Acceptance workflow: `.github/workflows/node-03-infrastructure.yml`

## Required evidence

NODE-03 is not COMPLETE until a clean GitHub Actions run proves all of the following:

- Docker Compose model validates.
- `make infra-up` starts PostgreSQL/pgvector, Redis, RabbitMQ, MinIO, and Mailpit from a clean runner.
- Every long-running Compose service becomes healthy.
- `make doctor` returns PASS.
- PostgreSQL `SELECT 1`, pgvector, and the local app/migration roles are available.
- Redis PING succeeds.
- RabbitMQ broker and management readiness succeed.
- MinIO creates `lumi-assets`, `lumi-exports`, and `lumi-sandbox`.
- MinIO PUT/GET round trip succeeds.
- Mailpit receives an SMTP message and exposes it through its API.
- PostgreSQL and MinIO data survive a container restart.
- `make infra-reset` refuses to run unless `CONFIRM=1` is explicit.
- `make infra-down` safely stops services without deleting volumes.

When green, this report will record the implementation commit, workflow run/job IDs, acceptance results, and any non-blocking warnings.
