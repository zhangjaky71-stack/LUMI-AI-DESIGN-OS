# Queue & Event Runtime V1

> NODE-19 runtime implementation contract.  
> Scope: RabbitMQ topology, Celery media jobs, transactional Outbox dispatch, Inbox dedupe, retry/DLQ, cancellation checkpoints.

## 1. Runtime split

LUMI uses two message semantics and does not collapse them into one abstraction:

- **Jobs** are commands to perform work. They are routed through the direct exchange `lumi.jobs` and have retry/cancellation state in a business record (`tasks`, `asset_validation_runs`, or a concrete generation record).
- **Domain Events** are immutable facts. They are created in PostgreSQL `outbox_events`, published to the topic exchange `lumi.domain`, and deduplicated per consumer in `inbox_events`.

The broker is transport, not the business source of truth.

## 2. RabbitMQ topology

| Type | Name | Routing |
|---|---|---|
| Direct exchange | `lumi.jobs` | job queue routing |
| Topic exchange | `lumi.domain` | domain event name |
| Topic DLX | `lumi.dlx` | `<source-queue>.dead` |
| Queue | `lumi.media.image` | image transforms |
| Queue | `lumi.media.video` | video renders |
| Queue | `lumi.media.export` | export packaging |
| Queue | `lumi.asset.processing` | asset validation/preview |
| Queue | `lumi.domain.<consumer>` | consumer-specific domain subscriptions |
| DLQ | `<source-queue>.dlq` | poison/permanent failures |

Topology declaration is idempotent through `lumi_worker_media.topology.declare_topology`.

## 3. Job contract

Broker payloads are ID-only/small JSON. `JobMessage` carries:

```json
{
  "job_id": "uuid",
  "organization_id": "uuid",
  "project_id": "uuid",
  "operation_id": "uuid-or-null",
  "trace_id": "optional-string"
}
```

Hard guardrails:

- maximum serialized job message: 64 KiB;
- bytes/binary values are rejected;
- secret-like fields (`secret`, `password`, `api_key`, `access_token`) are rejected;
- provider payloads and media binary must live in PostgreSQL/object storage, not RabbitMQ.

## 4. Job state and cancellation

Generic runtime jobs use the existing `tasks` record. Asset validation continues to use `asset_validation_runs`. This avoids a second competing `jobs` state machine.

Supported observable states remain `pending`, `running`, `retrying`, `succeeded`, `failed`, `cancelled`. Workers check cancellation before claim and before commit at safe checkpoints. Third-party provider cancellation/reconciliation remains a provider-specific concern and is completed in NODE-20/22.

## 5. Retry policy

Errors are classified as **transient**, **permanent**, or **cancelled**. Transient errors use bounded exponential backoff with jitter. Video retry policy explicitly carries `provider_reconciliation_required=true` so a future provider adapter must query provider state before an expensive retry.

NODE-19 deliberately keeps Celery `task_acks_late=false` and `task_reject_on_worker_lost=false`. Exactly-once is not claimed. NODE-20 must land idempotent side-effect reconciliation before late ACK/redelivery is enabled for cost-bearing tasks.

## 6. Outbox dispatcher

The always-on dispatcher splits the shared `outbox_events` table into two explicit channels:

- `MediaJobOutboxDispatcher`: only `event_name = 'job.dispatch.requested'`;
- `OutboxDispatcher`: all domain events where `event_name <> 'job.dispatch.requested'`.

Both channels use row locking only for the publish transaction:

```text
SELECT unpublished rows
FOR UPDATE SKIP LOCKED
→ increment publish_attempts
→ publish with RabbitMQ publisher confirm when available
→ on success set published_at
→ commit
```

Broker failure is deliberately handled **inside** the transaction boundary. The failed row's `publish_attempts + 1` is committed first, `published_at` remains `NULL`, and the original publisher error is re-raised only after the transaction exits. This prevents retry evidence from disappearing through rollback while preserving fail-closed process behavior.

A crash after broker acceptance but before `published_at` can still produce a duplicate. This is intentional at-least-once behavior and is absorbed by downstream idempotency/Inbox uniqueness. Exactly-once broker delivery is not claimed.

### 6.1 Operational health snapshot

Each dispatcher exposes a bounded read-only queue-head snapshot. It does **not** run `COUNT(*)` and does **not** lock rows:

```text
oldest pending row only
ORDER BY created_at, id
LIMIT 1
→ oldest_unpublished_age_seconds
→ oldest_publish_attempts
```

The CLI samples both job and domain queue heads after every dispatch cycle and emits one bounded JSON record with kind `lumi.outbox_dispatcher.health`. The general fields are the maximum of the two channels:

- `oldest_unpublished_age_seconds = max(job_age, domain_age)`;
- `oldest_publish_attempts = max(job_attempts, domain_attempts)`.

Channel-specific job/domain fields are retained for diagnosis. Exception strings, database DSNs and broker credentials are never serialized into the health payload. A failed cycle emits its health record before the dispatcher exits fail-closed.

Staging and Production derive CloudWatch metrics from these general fields. The current operational alarms are:

- oldest unpublished age `>= 300s` for two 60-second evaluation periods;
- oldest publish attempts `>= 5` for one 60-second evaluation period.

The alarms use `Maximum`, which is required because Production runs two dispatcher replicas and either replica may observe the unhealthy queue head.

## 7. Consumer runtime

Per domain event:

```text
validate envelope
→ parse tenant/event identity
→ INSERT inbox row ON CONFLICT DO NOTHING
→ run handler in the same PostgreSQL transaction
→ commit
→ ACK RabbitMQ message
```

If the Inbox insert conflicts, the message is acknowledged as `DUPLICATE` without replaying effects.

## 8. DLQ and admin evidence

Permanent failures are both:

1. rejected with `requeue=false` so RabbitMQ dead-letters them to `<source-queue>.dlq`;
2. persisted to `dead_letter_records` with message ID, tenant, queue, consumer, exchange/routing key, error category/code, attempts, trace ID, payload and timestamps.

This database record is the future NODE-64 Admin source. Replay marks `replayed_at`; UI is intentionally deferred.

## 9. Backpressure

Image, video, export and asset-processing queues are isolated. Worker deployments can scale concurrency independently. The default worker prefetch multiplier is `1`, preventing one worker process from reserving a large batch of expensive media jobs.

Dynamic ECS autoscaling remains disabled in the current release until NODE-69 has measured capacity evidence and a real production metric emitter. The outbox dispatcher therefore runs at explicit static capacity: one replica in Staging and two in Production.

## 10. Security

- RabbitMQ credentials come from environment configuration.
- Broker payloads are JSON only.
- Provider secrets and binary media are explicitly blocked from job messages.
- Domain envelopes are treated as untrusted input and validated before handler execution.
- Tenant IDs are bound into Inbox/Outbox persistence.
- The outbox dispatcher receives only PostgreSQL and RabbitMQ secrets, no provider/model/sandbox/auth/search credentials and no S3 IAM capability.
- Production/Staging dispatcher networking uses the restricted VPC egress branch rather than arbitrary public Internet egress.

## 11. Verification

Required gates:

```bash
python scripts/validate_queue_runtime_contract.py
python scripts/validate_outbox_dispatcher_observability.py
uv run pytest apps/worker-media/tests -q
uv run ruff check apps/worker-media apps/api/src/lumi_api/persistence scripts/validate_queue_runtime_contract.py
uv run pyright
make infra-env
make infra-up
make db-upgrade
bash scripts/db-local schema-check
```

Hosted integration additionally exercises RabbitMQ topology, Celery sample delivery, durable Outbox publish-attempt accounting, duplicate Inbox suppression, permanent DLQ, queue separation, and the PostgreSQL-backed queue/event state.

The current repository contract is source-complete for these behaviors, but release acceptance still requires trusted executable evidence from the frozen dependency graph, PostgreSQL, RabbitMQ, Docker and Terraform environments.
