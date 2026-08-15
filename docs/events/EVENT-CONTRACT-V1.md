# LUMI AI Design OS — Event / Message Contract V1

> Node: NODE-12  
> Status: IMPLEMENTED / VALIDATING  
> Date: 2026-08-16  
> Executable contract: `apps/api/src/lumi_api/events/`

## 1. Purpose

NODE-12 freezes the asynchronous fact contract shared by API/application services, Agent runtime, workers, providers, artifact processing, billing and later realtime transports.

The contract is broker-neutral. Kafka/NATS/Redis Streams/queues may carry these facts later, but broker offsets, retry counters and delivery handles are transport metadata and are **not** fields in the immutable domain event.

Events are past-tense facts. They are not hidden commands.

```text
command: GenerateImage        (request to do something)
event:   generation.completed (fact that something happened)
```

Task/worker command envelopes are deferred to the worker/runtime implementation. NODE-12 does not overload domain events as a queue RPC protocol.

## 2. Delivery guarantee

LUMI V1 assumes **at-least-once delivery**.

Consequences:

1. a producer may publish the same event more than once;
2. consumers must be idempotent;
3. NODE-10 `inbox_events(event_id, consumer)` is the durable consumer dedupe identity;
4. NODE-10 `outbox_events` is the transactional producer boundary;
5. no subsystem may claim globally exactly-once delivery.

Application-level exactly-once *effects* may be achieved for specific operations through idempotency/unique constraints, but that is not the same as exactly-once transport delivery.

## 3. Immutable envelope

Canonical envelope:

```json
{
  "spec_version": "lumi.events/1.0",
  "event_id": "0191...",
  "event_type": "lumi.project.created.v1",
  "occurred_at": "2026-08-16T00:00:00Z",
  "organization_id": "0191...",
  "aggregate_type": "project",
  "aggregate_id": "0191...",
  "aggregate_version": 1,
  "producer": "lumi.api",
  "correlation_id": "request-123",
  "causation_id": null,
  "traceparent": null,
  "payload": {}
}
```

### Required identity

```text
spec_version
event_id
event_type
occurred_at
organization_id
aggregate_type
aggregate_id
producer
payload
```

### Optional causal/ordering metadata

```text
aggregate_version
correlation_id
causation_id
traceparent
```

### Explicitly excluded from the event

```text
broker topic/stream
partition number
broker offset
consumer group
delivery attempt
retry_at
DLQ reason
published_at
raw provider credentials
large binary payloads
ORM/session objects
LangGraph checkpoint state
```

Those belong to transport/runtime storage, not the immutable business fact.

## 4. Event identity

`event_id` is application-generated UUIDv7-compatible identity from NODE-09.

Rules:

- one logical fact has one `event_id`;
- broker retries preserve it;
- Outbox publication retries preserve it;
- replay preserves it;
- consumers dedupe by `(event_id, consumer)`;
- generating a fresh event ID for the same historical fact merely to bypass dedupe is forbidden.

A genuinely new compensating/corrective fact gets a new event ID and references the prior cause through payload/causation semantics where appropriate.

## 5. Event type naming/versioning

Format:

```text
lumi.<bounded-context-or-aggregate>.<fact>.v<major>
```

Examples:

```text
lumi.project.created.v1
lumi.asset.ready.v1
lumi.agent_run.started.v1
lumi.artifact.version_created.v1
```

Rules:

1. past-tense fact naming;
2. lowercase snake/dot-compatible segments;
3. major payload semantics are encoded in `.vN`;
4. additive optional fields may be added compatibly within v1;
5. changing meaning, removing a field, changing a required field/type or reinterpreting units requires `.v2`;
6. v1 consumers must reject an unknown major event type rather than guessing.

`spec_version` versions the envelope; `.vN` versions a specific event payload. They are independent compatibility axes.

## 6. Frozen P0 event catalogue

### `lumi.project.created.v1`

Aggregate: `project`.

Payload:

```text
project_id
workspace_id
project_version
```

### `lumi.asset.ready.v1`

Aggregate: `asset`.

Payload:

```text
asset_id
project_id?
mime_type
checksum_sha256
```

The event references stored content. It does not embed file bytes or signed storage credentials.

### `lumi.agent_run.started.v1`

Aggregate: `agent_run`.

Payload:

```text
agent_run_id
project_id
thread_id
graph_version
agent_config_version
```

### `lumi.agent_run.waiting_user.v1`

Aggregate: `agent_run`.

Payload:

```text
agent_run_id
project_id
interaction_id
reason_code
```

The payload deliberately does not embed the user's full prompt/transcript. Consumers retrieve authorized state by ID if needed.

### `lumi.task.succeeded.v1`

Aggregate: `task`.

Payload:

```text
task_id
project_id
output_artifact_version_ids[]
```

### `lumi.generation.completed.v1`

Aggregate: `generation`.

Payload:

```text
generation_id
project_id
operation_id
provider
model
output_artifact_version_ids[]
```

Provider/model are traceability facts. Provider-native response blobs do not belong in this event.

### `lumi.artifact.version_created.v1`

Aggregate: `artifact` or the producing artifact-version stream, with a stable aggregate policy selected by the producer and used consistently.

Payload:

```text
artifact_id
artifact_version_id
branch_id
version_number
```

### `lumi.artifact.approved.v1`

Aggregate: `artifact_version`.

Payload:

```text
artifact_version_id
approval_id?
actor_id?
```

### `lumi.cost.recorded.v1`

Aggregate: `cost_entry`.

Payload:

```text
cost_entry_id
operation_id
amount Decimal
currency
kind = charge | reversal | adjustment
```

Money serializes as a decimal string in canonical JSON and must never be converted through binary float.

## 7. Producer transaction: Outbox

The producer pattern is:

```text
BEGIN
  mutate domain/business rows
  build immutable EventEnvelope
  insert outbox row using the same event_id
COMMIT
```

NODE-10 Outbox is persisted in the same PostgreSQL transaction as the business mutation.

`project_to_outbox()` maps:

```text
event_id         → outbox identity
organization_id  → tenant scope
event_type       → routing/schema key
aggregate_type   → aggregate family
aggregate_id     → aggregate identity
occurred_at      → historical fact time
envelope_json    → full canonical event
```

The publisher may add operational publication timestamps/attempt counts to the **outbox row**, but those are not allowed to mutate the canonical envelope.

## 8. Consumer transaction: Inbox

Consumer pattern:

```text
receive event
BEGIN
  INSERT inbox_events(event_id, consumer)
    -- unique identity; duplicate means already processed
  validate event type/schema
  execute idempotent consumer effect
COMMIT
ack transport delivery
```

If the transaction fails, the transport may redeliver. If the inbox insert already exists, the consumer can acknowledge without reapplying the effect.

Consumer identity is versioned when processing semantics change, for example:

```text
artifact-indexer.v1
artifact-indexer.v2
```

This gives an explicit replay namespace.

## 9. Replay

Replay is a transport/operations action over historical immutable events.

Rules:

- preserve original `event_id`;
- preserve original `occurred_at`;
- preserve original event type/payload;
- delivery timestamp/attempt may differ outside the envelope;
- normal same consumer identity will dedupe already processed events;
- intentional full reprocessing uses a **new consumer identity/replay namespace**, not a fabricated new event ID;
- replay must honor current authorization/data-retention restrictions;
- replay of an old event must not be misreported as a newly occurred business fact.

## 10. Ordering

There is no global event order.

LUMI only defines a stable aggregate-local partition key:

```text
org:<organization_id>:aggregate:<aggregate_type>:<aggregate_id>
```

A compatible transport should keep events with the same key in the same ordered partition/stream when it offers that feature.

`aggregate_version`, when present, expresses the source aggregate version and can detect gaps/out-of-order processing.

Rules:

- never compare UUIDv7 timestamps as a substitute for business ordering;
- never infer cross-aggregate causality from broker offset or wall-clock ordering;
- use `causation_id` / `correlation_id` / domain references for causal analysis.

## 11. Correlation and causation

### `correlation_id`

Groups a workflow/request across multiple facts, e.g. one HTTP request or AgentRun workflow.

It is a bounded opaque string because NODE-11 request IDs may be client-generated rather than UUIDs.

### `causation_id`

When an event was directly caused by a previous event, this references the causal event's UUID.

### `traceparent`

Optional W3C-style trace correlation string. It supports observability only and is not domain identity.

## 12. Privacy and payload minimization

Events can be copied, retried, retained and replayed, so payloads must be smaller and safer than application state.

P0 rules:

- no credentials/tokens/secrets;
- no signed object-storage URLs;
- no raw binary/image/video content;
- no full user prompt/transcript by default;
- no provider raw response dump;
- no ORM/provider/runtime objects;
- prefer tenant-owned resource IDs + safe normalized metadata;
- sensitive details are fetched at processing time through authorized services when required.

## 13. Schema validation

Every registered event type maps to one immutable strict Pydantic payload model.

Unknown extra fields are rejected by the executable v1 models today. Compatible producer additions therefore require coordinated contract evolution/tests before rollout; they must not be sprayed into production first and documented later.

Consumers must choose one of these explicit policies per deployment:

```text
strict current-v1 consumer
version-tolerant adapter/upcaster
new consumer identity for new semantics
```

The registry never guesses an unknown event version.

## 14. Failure / retry / DLQ

Retry behavior is transport policy, not event payload semantics.

A delivery wrapper/runtime may track:

```text
attempt
first_seen_at
last_error_code
next_retry_at
dead_lettered_at
broker coordinates
```

These must not rewrite `EventEnvelope`.

Retryable vs terminal classification belongs to the consumer/transport adapter. Dead-lettering preserves the original canonical event and records failure metadata separately.

## 15. HTTP / realtime relationship

NODE-11 HTTP asynchronous operations return product resources with `202 Accepted`, e.g. AgentRun/Generation.

NODE-12 provides the facts that a later SSE/WebSocket/realtime adapter can expose in a client-safe stream. This node does **not** freeze broker topics as public API and does not promise raw internal events will be sent directly to browsers.

A future client event stream should transform/redact internal events through an explicit public realtime contract.

## 16. Broker neutrality

`lumi_api.events` must not import:

```text
Kafka clients
NATS clients
Redis clients
Celery
SQLAlchemy / asyncpg / Alembic
LangGraph / LangChain
provider SDKs
object-storage SDKs
```

The event package owns schemas/semantics only. Transport adapters depend on it, not vice versa.

## 17. Definition of Done

NODE-12 becomes COMPLETE only when:

```text
immutable envelope
+ 9 P0 event payloads/registry
+ Outbox projection
+ Inbox consumer identity
+ at-least-once/idempotency/replay rules
+ aggregate-local ordering contract
+ privacy/versioning contract
+ executable schema/round-trip tests
+ broker/runtime dependency purity
+ repository CI/security green
+ stacked NODE-09/10/11 dependencies resolved
+ merged and NODE index updated
```

Until then it remains `VALIDATING` or `BLOCKED_EXTERNAL / VALIDATING` according to evidence.
