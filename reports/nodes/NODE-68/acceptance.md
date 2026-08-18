# NODE-68 Acceptance — Backup, Recovery & Disaster Readiness

## Status

**CORE IMPLEMENTED / VALIDATING / NOT COMPLETE**

Implementation evidence and recovery-drill evidence are intentionally separate. This branch implements a conservative recovery decision core over existing PostgreSQL/runtime/provider/Agent/Artifact truth. It does **not** claim that production PITR, object restore, regional failover or RPO/RTO targets have been proven.

## Implemented core

- `RecoveryDisposition` policy: `REQUEUE_SAFE`, `RESUME_SAFE`, `RECONCILE_EXTERNAL`, `VERIFY_OBJECT`, `REVIEW_REQUIRED`, `TERMINAL`, `SKIP`;
- Postgres scanner over existing `runtime_jobs`, `idempotency_operations`, `agent_run_control` and exact graph definitions;
- no RabbitMQ or Redis dependency in recovery truth scanning;
- runtime job status handling uses the real NODE-19 states: `pending/running/retrying/succeeded/failed/cancelled`;
- runtime `operation_id` is treated as optional/non-FK evidence; it is only trusted when a same-organization IdempotencyOperation row actually resolves;
- known `provider_request_id` is always reconciled, never replaced with a new provider request;
- active durable idempotency lease is not stolen;
- paid side effect without native provider identity is `REVIEW_REQUIRED`;
- paid-capable `image.transform` / `video.render` without durable idempotency evidence is not generically requeued;
- known safe `asset.preview`, `asset.validate` and idempotent `export.package` pending work can be redispatched using the existing runtime job identity;
- Agent recovery checks exact `graph_key/version/hash`, enabled graph definition, checkpoint identity and `resume_version`;
- `waiting_user` is preserved rather than auto-resumed;
- `waiting_external` routes to reconciliation and requires a durable checkpoint;
- Artifact object verification uses internal `bucket/storage_key/size/SHA-256` only;
- signed/public URLs are explicitly rejected as recovery truth;
- RPO/RTO model cannot report target met without measured data-loss and restore-duration evidence;
- execution ports only permit actions that preserve existing durable job/run/provider identities.

## Deterministic tests

Committed tests cover:

1. running paid job without provider identity requires review;
2. known provider request produces `RECONCILE_EXTERNAL` and preserves operation/provider ids;
3. active paid lease is not stolen;
4. pending paid-capable job without idempotency proof is not automatically requeued;
5. safe asset preview work can be redispatched;
6. paid retryable operation without provider request remains review-required;
7. Agent graph-definition hash mismatch blocks resume;
8. `waiting_user` remains waiting;
9. running Agent requires durable checkpoint;
10. object checksum mismatch is explicit failure/review evidence;
11. signed URL cannot enter object recovery evidence;
12. RPO/RTO targets are not considered achieved without measurements;
13. external reconciliation reuses existing ids;
14. review decisions cannot execute side effects.

## Production gates still open

- PostgreSQL backup/PITR restore drills and measured RPO/RTO;
- object versioning/replication and checksum restore adapter/drill;
- production NODE-19 redispatch composition and empty-broker rebuild drill;
- production Agent checkpoint resume composition;
- provider-specific reconciliation and callback-loss drills;
- immutable drill/action evidence persistence after exact Alembic head verification;
- deploy/schema rollback and forward-fix drills;
- regional/site recovery;
- runbooks, escalation owners and scheduled exercises;
- latest-head Hosted validation that actually executes commands.

## Truth rules

- PostgreSQL is business truth; RabbitMQ and Redis are rebuildable operational state.
- Object storage internal key/checksum metadata is binary truth; signed URLs are not.
- Existing `operation_id`, `provider_request_id`, AgentRun/checkpoint identities must be preserved.
- Unknown paid side effects never auto-rerun.
- Configuration is not recovery evidence. Only measured drills can close RPO/RTO acceptance.
