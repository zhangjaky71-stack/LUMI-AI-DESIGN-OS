# NODE-19 — Queue / Event Runtime Acceptance

Status: **IMPLEMENTED / VALIDATING**  
Hosted status: **not PASS until a runner actually executes the workflow**

## Implemented

- RabbitMQ direct job exchange, topic domain exchange and DLX.
- Separate image/video/export/asset queues plus DLQs.
- Quorum domain-consumer queues with delivery limit and backpressure limits.
- JSON-only, IDs-only P0 JobMessage with 64 KiB ceiling and secret/binary rejection.
- Durable Job state contract and type-specific retry policy.
- Provider reconciliation safety gate for video retries.
- Database cancellation semantics.
- Celery task routes for all five P0 job kinds.
- `acks_late=false` and explicit stale-running crash recovery rather than pretending all tasks are late-ack safe.
- Exact NODE-12 `lumi.events/1.0` validation on broker ingress.
- Valid fixtures for all nine frozen NODE-12 v1 event payload contracts.
- Project/Asset internal-event to NODE-12 canonical-envelope bridge.
- Tenant-sharded Outbox dispatcher with `FOR UPDATE SKIP LOCKED`.
- Publisher confirms / durable messages.
- Inbox `(event_id, consumer)` dedupe with handler effect in the same transaction.
- Permanent Domain Event DLQ plus malformed-identity broker quarantine.
- Explicit permanent Job DLQ persistence + `lumi.dlx` publication despite `acks_late=false`.
- Tenant-scoped Domain Event replay preserving original `event_id`.
- Tenant-scoped Job replay through the Celery task protocol preserving original `job_id`.
- NODE-18 `asset.validate` Job scheduling wrapper.
- Forward Alembic migration `20260816_0005`.
- RLS on `runtime_jobs` and `dead_letter_records`.
- Runtime Job Project same-tenant trigger.
- PostgreSQL, RabbitMQ and real Celery worker acceptance scripts.
- Failure-injection unit tests for duplicate dispatch, receipt rollback, transient/permanent retry, Job DLQ, cancellation and stale worker recovery.
- Three generated JSON schemas.

## Canonical source checks

```bash
uv sync --all-packages --frozen
PYTHONPATH=apps/worker-media/src:apps/api/src uv run python tools/node19/validate_queue_runtime.py
PYTHONPATH=apps/worker-media/src:apps/api/src uv run pytest -q \
  apps/worker-media/tests/test_queue_runtime_contract.py \
  apps/worker-media/tests/test_event_runtime_contract.py \
  apps/worker-media/tests/test_event_schema_coverage.py \
  apps/worker-media/tests/test_job_dlq_contract.py \
  apps/worker-media/tests/test_safe_consumer_contract.py \
  apps/worker-media/tests/test_queue_topology_and_celery.py \
  apps/api/tests/test_queue_event_bridge.py
PYTHONPATH=apps/api/src uv run python tools/node19/export_queue_schemas.py
```

Hosted workflow must additionally:

```text
start PostgreSQL + RabbitMQ
upgrade through 0004
load deterministic two-tenant fixture
upgrade to 0005
run baseline DB invariants
run NODE-19 DB invariants
run real RabbitMQ domain/job/explicit Job-DLQ round trip
start real Celery worker with RabbitMQ + RPC result backend
run worker smoke
stop worker
alembic downgrade 0004
verify NODE-18 remains and NODE-19 objects are removed
alembic upgrade 0005
rerun NODE-19 DB invariants
```

## Evidence required before COMPLETE

- Python 3.12 frozen install green.
- Unit/failure-injection suite green.
- Static architecture validator green.
- Three schemas parse green.
- Ruff green.
- Pyright green.
- PostgreSQL migration/RLS/inbox/job/DLQ tests green.
- RabbitMQ real topology/routing/DLQ round trip green.
- Real Celery worker smoke green.
- Downgrade/reapply green.
- Repository CI/security green.
- Stacked NODE-09 through NODE-18 dependencies resolved.

## Explicit non-claims

- No exactly-once broker claim.
- No global event ordering claim.
- No claim that `acks_late` is safe for all task classes.
- No production PASS from a workflow that received no runner.
- Open integration gaps remain in `gap-ledger.json`.

## Completion rule

A GitHub job with `runner_id=0` and `steps=[]` is `BLOCKED_EXTERNAL`, not a source failure and not a PASS.

Next: **NODE-20 — Idempotency**.
