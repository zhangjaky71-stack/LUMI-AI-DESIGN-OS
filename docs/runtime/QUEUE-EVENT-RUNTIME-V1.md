# LUMI Queue / Event Runtime V1

Status: **FROZEN FOR NODE-19 VALIDATION**

## 1. Scope

NODE-19 turns the NODE-12 event contract and media/background work into a real asynchronous runtime. RabbitMQ transports work; PostgreSQL remains the durable business truth.

The runtime deliberately does **not** claim exactly-once delivery. The target semantics are:

- broker delivery: at least once;
- domain-event business effect: effectively once through `(event_id, consumer)` Inbox identity;
- job execution trigger: at least once;
- job state transition/effect: guarded by durable `runtime_jobs` claim state;
- publisher crash after broker acceptance may duplicate, never silently rewrite event identity.

## 2. Exchanges and queues

Exchanges:

```text
lumi.jobs   direct
lumi.domain topic
lumi.dlx    topic
```

P0 job queues:

```text
lumi.media.image
lumi.media.video
lumi.media.export
lumi.asset.processing
```

Every job queue has a `.dlq`. Domain consumers own durable queues named `lumi.domain.<consumer>` and corresponding `.dlq` queues.

Image/video/export/asset queues are physically separate so video work cannot starve small image or validation jobs.

## 3. Job message contract

Job messages contain IDs and small JSON only:

```text
job_id
organization_id
project_id
operation_id?
resource_id?
traceparent?
```

Forbidden:

- binary file bodies;
- provider secrets or credentials;
- authorization/access/refresh tokens;
- presigned/signed URLs;
- payloads over 64 KiB.

Files stay in NODE-18 object storage and are referenced by durable IDs.

## 4. Job state

```text
PENDING -> RUNNING -> SUCCEEDED
                  -> RETRYING -> RUNNING
                  -> FAILED
                  -> CANCELLED
```

`runtime_jobs` is authoritative. Celery result backends are not business truth.

Cancellation is a durable state request and cooperative checkpoint, not blind process termination.

## 5. Retry policy

Transient errors may retry with bounded exponential backoff plus deterministic jitter. Unknown errors fail closed as permanent unless explicitly marked retryable.

Video/provider jobs are special: before retrying a timed-out request, a provider reconciler must inspect the prior provider request. If reconciliation is unavailable, the runtime fails safe rather than creating an uncontrolled duplicate billable request.

## 6. Acknowledgement model

NODE-19 intentionally keeps:

```text
task_acks_late = false
task_reject_on_worker_lost = false
worker_prefetch_multiplier = 1
```

This follows the node specification: late acknowledgement is not enabled until all task classes prove safe replay behavior.

A hard worker crash is recovered by a PostgreSQL stale-running sweeper. The sweeper republishes stale work and moves it to RETRYING under tenant-scoped locking. Duplicate triggers remain safe because only an eligible durable job row can be claimed into RUNNING.

## 7. Domain event envelope

Broker events use the exact NODE-12 contract:

```text
spec_version = lumi.events/1.0
event_id
event_type
occurred_at
organization_id
aggregate_type
aggregate_id
aggregate_version?
producer
correlation_id?
causation_id?
traceparent?
payload
```

No CloudEvents replacement is introduced.

NODE-19 ships explicit bridges for NODE-17 `project.created` and NODE-18 `asset.ready` internal transaction events. The bridge creates the canonical `lumi.project.created.v1` / `lumi.asset.ready.v1` envelope while preserving the original internal event ID.

## 8. Outbox

The outbox dispatcher is tenant-sharded. It never bypasses NODE-16 RLS merely to scan all tenants.

Per organization:

```text
SET LOCAL app.current_organization_id
SELECT unpublished due rows
FOR UPDATE SKIP LOCKED
publish durable message with publisher confirms
mark published / or schedule retry
COMMIT
```

`payload_json` for broker-facing rows is the immutable canonical envelope, not just the event payload.

The crash window after broker acceptance but before `published_at` can cause duplicate publication. This is expected and covered by Inbox dedupe.

## 9. Inbox / consumer transaction

Consumer path:

```text
receive
-> validate exact envelope/version
-> derive tenant from validated envelope
-> BEGIN tenant transaction
-> INSERT inbox_events(event_id, consumer) ON CONFLICT DO NOTHING
-> if duplicate: commit + ack
-> apply business effect using the same DB transaction/connection
-> commit
-> ack
```

If the handler fails, both Inbox receipt and effect roll back.

## 10. Poison messages and DLQ

Permanent valid-identity failures are recorded in tenant-scoped `dead_letter_records`.

If a malformed message has no trustworthy organization/event ID, it cannot safely be written into a tenant table. `SafeKombuEventConsumer` sends it to broker quarantine/DLX and rejects it without requeue, preventing poison loops.

DLQ replay:

- is tenant scoped;
- republishes the original payload/routing identity;
- preserves the original `event_id` / `job_id`;
- creates no new domain identity;
- marks one DLQ record replayed so the same operator action is not silently repeated.

## 11. NODE-18 Asset validation scheduling

`QueuedAssetApiService` wraps the NODE-18 API service. Successful upload completion schedules an IDs-only `asset.validate` request using `upload_id` as `resource_id`.

The API package depends only on the `JobScheduler` protocol and never imports the worker package. Production composition can bind a durable scheduler without coupling FastAPI domain code to Celery.

## 12. PostgreSQL `0005`

Forward migration only:

```text
20260816_0004 -> 20260816_0005
```

Adds:

- Outbox publish attempt/error/next-at fields;
- `runtime_jobs`;
- `dead_letter_records`;
- tenant RLS;
- runtime-job Project same-tenant trigger;
- query indexes;
- least-privilege app grants.

NODE-10 through NODE-18 migrations are not rewritten.

## 13. Backpressure

Controls:

- physical queue separation;
- `worker_prefetch_multiplier=1`;
- queue byte limits;
- `reject-publish` overflow;
- quorum domain queues with delivery limit;
- bounded retries;
- DLQ rather than infinite retries.

Concurrency by worker class is deployment configuration and must be tuned against provider limits, memory, CPU/GPU, and cost budgets.

## 14. Security

- tenant IDs in messages are validated, then DB RLS is set from that validated identity;
- API never trusts broker payload to bypass tenant checks;
- no secrets or signed URLs in broker messages;
- no pickle serializer;
- malformed identities use non-tenant quarantine;
- DLQ replay is tenant scoped.

## 15. Guarantees and non-guarantees

Guaranteed by contract once canonical validation passes:

- durable DB job truth;
- explicit retry classification;
- duplicate-safe event consumer identity;
- tenant-scoped runtime state;
- canonical NODE-12 broker envelope;
- operator-visible DLQ/replay path;
- no large/binary broker payloads.

Not claimed:

- global event ordering;
- exactly-once broker delivery;
- generic automatic retry of every provider call;
- late-ack safety for all media tasks;
- production completion while hosted validation has not executed.

## 16. Runtime gaps carried forward

See `reports/nodes/NODE-19/gap-ledger.json`. The largest remaining runtime integration gaps are production frozen `asyncpg` dependency/composition and replacing placeholder media task handlers with real NODE-18 storage/validation adapters once its SQL repository binding exists.

Next: **NODE-20 — Idempotency**.
