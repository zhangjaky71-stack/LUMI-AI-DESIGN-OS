# LUMI AI Design OS — Event Contract V1

> Node: `NODE-12`  
> Status: **IMPLEMENTED / VALIDATING / BLOCKED_EXTERNAL**  
> Contract root: `contracts/events/v1`  
> Reference runtime: `services/event-contract`  
> Broker baseline: RabbitMQ topic exchange

---

## 1. Purpose

NODE-12 defines the contract between business/domain events and asynchronous message delivery.

It deliberately separates:

```text
Domain Event
    ↓ mapping
LUMI Event Envelope
    ↓ transactional outbox
Broker Message
    ↓ consumer inbox/dedupe
Consumer application logic
```

The broker message is not the domain aggregate and the DomainEvent object is not serialized directly as an arbitrary Python object.

## 2. Delivery semantics

LUMI V1 promises:

```text
at-least-once delivery
```

It does **not** promise:

```text
exactly-once delivery
exactly-once side effects
global event ordering
```

Exactly-once claims are rejected because network retries, publisher confirms, broker redelivery and consumer crashes can produce duplicates.

Correctness is achieved through:

```text
producer transaction + outbox
at-least-once broker delivery
consumer transaction + inbox dedupe
idempotent side effects
```

## 3. Ordering semantics

Ordering scope is:

```text
partitionkey
```

Consumers may reason about order only when events use the same partition key and the delivery path preserves that partition order.

Consumers must never rely on global ordering across unrelated projects/assets/tasks/generations.

## 4. Event registry

Registry:

```text
contracts/events/v1/registry.json
```

V1 exchange:

```text
lumi.events.v1
```

Dead-letter exchange contract:

```text
lumi.events.v1.dlx
```

Each registered event defines:

```text
name
type
owner_context
routing_key
schema_version
payload_schema
partition_field
subject_template
```

Producer code must load the registry and may not invent routing keys independently.

## 5. Frozen V1 vocabulary

NODE-12 reuses the NODE-09 domain event vocabulary exactly:

```text
project.created
asset.ready
agent_run.started
agent_run.waiting_user
artifact.version_created
artifact.approved
task.succeeded
generation.completed
cost.recorded
```

Public broker types are:

```text
lumi.project.created
lumi.asset.ready
lumi.agent_run.started
lumi.agent_run.waiting_user
lumi.artifact.version_created
lumi.artifact.approved
lumi.task.succeeded
lumi.generation.completed
lumi.cost.recorded
```

Routing key equals the stable domain event name.

## 6. Envelope V1

The envelope uses CloudEvents-compatible core attribute names plus LUMI extensions.

Example:

```json
{
  "specversion": "1.0",
  "id": "01900000-0000-7000-8000-000000000101",
  "source": "lumi://api/projects",
  "type": "lumi.project.created",
  "subject": "project/01900000-0000-7000-8000-000000000006",
  "time": "2026-08-13T01:00:00Z",
  "datacontenttype": "application/json",
  "dataschema": "urn:lumi:event:project.created:1",
  "organizationid": "01900000-0000-7000-8000-000000000001",
  "correlationid": "01900000-0000-7000-8000-000000000102",
  "causationid": null,
  "traceid": null,
  "partitionkey": "project_id:01900000-0000-7000-8000-000000000006",
  "schemaversion": 1,
  "data": {
    "project_id": "01900000-0000-7000-8000-000000000006",
    "workspace_id": "01900000-0000-7000-8000-000000000004",
    "name": "Campaign"
  }
}
```

## 7. Required envelope fields

Required:

```text
specversion
id
source
type
subject
time
datacontenttype
dataschema
organizationid
correlationid
partitionkey
schemaversion
data
```

Optional:

```text
causationid
traceid
```

The top-level envelope has:

```text
additionalProperties = false
```

New envelope attributes therefore require an explicit contract change rather than accidental producer-specific fields.

## 8. Tenant identity

Every event carries:

```text
organizationid
```

This is the durable tenant ownership of the event.

Consumers must not derive tenant identity from payload/project ID alone.

A consumer must reject or quarantine an event when the envelope tenant conflicts with the tenant of a referenced durable resource.

## 9. Correlation and causation

### correlationid

Groups events/operations belonging to one business flow.

Examples:

```text
user command
agent run
workflow operation
```

### causationid

Points to the immediate predecessor event/command identity when one event caused another.

Rule:

```text
correlationid may stay constant across a workflow
causationid changes along the causal chain
```

This supports timeline reconstruction without pretending timestamps alone establish causality.

## 10. Trace ID

`traceid` is optional infrastructure observability metadata.

It may map to OpenTelemetry/LangSmith tracing later, but consumers must not use trace ID as business identity or dedupe key.

## 11. Event ID and dedupe

`id` is the immutable event identity.

Consumer dedupe uses:

```text
(consumer, event_id)
```

which maps to NODE-10 `inbox_events` uniqueness.

Retries/redelivery preserve the same event ID.

A new event describing a new fact receives a new event ID.

## 12. Retry metadata

Delivery attempt is not stored inside the immutable event envelope.

Broker headers include:

```text
x-lumi-event-id
x-lumi-schema-version
x-lumi-correlation-id
x-lumi-causation-id?
x-lumi-trace-id?
x-lumi-delivery-attempt
```

A broker retry may change `x-lumi-delivery-attempt` while the envelope bytes remain unchanged.

## 13. Payload schema strategy

Each event has a JSON Schema 2020-12 payload file:

```text
contracts/events/v1/payloads/<event-name>.schema.json
```

Every payload schema uses:

```text
additionalProperties = true
```

This is an intentional forward-compatibility rule: consumers must ignore additive fields they do not understand.

## 14. Schema versioning

Each definition has integer:

```text
schemaversion >= 1
```

and canonical schema URI:

```text
urn:lumi:event:<event-name>:<version>
```

### Compatible V1 evolution

Usually backward-compatible:

- add optional field;
- add enum value only when consumer behavior tolerates unknown values;
- relax validation without changing semantic meaning.

### Breaking evolution

Requires a new schema version:

- remove field;
- rename field;
- change field type;
- make optional field required;
- change units/meaning of an existing field;
- change partition semantics;
- change subject identity semantics.

Producer rollout must keep old consumers compatible during the migration window.

## 15. Payload minimization

Events carry facts, not database snapshots.

Forbidden pattern:

```text
SELECT * row
→ serialize entire row
→ broker
```

Event payloads should include:

- stable IDs;
- changed/important business facts;
- version/model identifiers when consumers need them.

They should not include:

- API keys;
- passwords;
- access/refresh tokens;
- authorization headers;
- provider raw responses;
- entire Design IR documents;
- media binary bytes.

The validator rejects secret-like top-level payload property names.

## 16. Cost event precision

`cost.recorded.amount` is a decimal string:

```json
"0.12345678"
```

not a JSON floating-point number.

This preserves the NODE-09/NODE-10 Decimal/NUMERIC financial invariant across the event boundary.

## 17. Producer transaction

Correct producer sequence:

```text
BEGIN DATABASE TRANSACTION
  apply business mutation
  insert outbox_events row with immutable event ID/payload
COMMIT
```

The broker publisher runs after commit and publishes pending outbox rows.

Producer code must not:

```text
commit DB mutation
publish broker event
```

as two unrelated operations without outbox protection.

NODE-10 already provides the durable Outbox table and shared-session insertion primitive.

## 18. Publisher semantics

Outbox publisher requirements for later implementation:

- read unpublished rows in deterministic order;
- publish event envelope to registry exchange/routing key;
- use publisher confirms;
- mark `published_at` only after accepted broker publish;
- tolerate publisher crash after broker accept but before DB mark;
- therefore duplicates remain possible and expected;
- increment publish attempts separately from immutable envelope data.

NODE-19 owns the concrete dispatcher/publisher implementation.

## 19. Consumer transaction

Expected consumer flow:

```text
receive event
→ validate envelope/schema support
→ BEGIN
→ INSERT inbox_events(consumer,event_id)
→ if conflict: duplicate -> ACK without side effect
→ execute idempotent business effect
→ COMMIT
→ ACK
```

If processing fails before commit, the broker may redeliver.

External non-transactional side effects require their own idempotency keys/reconciliation strategy.

## 20. Dead-letter policy

A message belongs in dead-letter handling when the failure is not expected to succeed through immediate retry, for example:

```text
unsupported schema version
invalid envelope
invalid payload
non-retryable consumer error
retry budget exhausted
```

Dead-lettering must preserve original event identity and diagnostic reason.

NODE-19/54 own concrete retry delay, queue topology and operational tooling.

## 21. Consumer compatibility

A consumer must explicitly define supported event name/schema versions.

Recommended startup validation:

```text
consumer subscribes to event X
→ registry contains X
→ supported schema version includes producer version
→ queue binding exists
```

Unknown newer schema versions must fail safely rather than being interpreted using an older incompatible parser.

## 22. Reference runtime

Package:

```text
services/event-contract/src/lumi_event_contract
```

Runtime dependencies:

```text
Python standard library only
```

It provides:

```text
EventEnvelope
EventDefinition
EventRegistry
load_registry()
validate_payload()
build_envelope()
broker_headers()
```

`EventEnvelope` is frozen and deep-freezes nested payload data.

## 23. Validation tooling

```bash
python scripts/validate_event_contracts.py
```

Validator checks:

- exactly 9 frozen domain events;
- event type/routing key uniqueness;
- bounded-context ownership;
- schema `$id` and version;
- JSON Schema draft;
- required partition field;
- subject fields are required facts;
- payload additive compatibility;
- secret/raw-response field guard;
- decimal-string cost amount;
- at-least-once and partition ordering declarations.

## 24. Dependency-free CI gate

Workflow:

```text
.github/workflows/event-contract.yml
```

It requires only hosted Python 3.12:

```text
compileall
→ validate_event_contracts.py
→ stdlib unittest
```

It intentionally does not depend on `uv.lock`, PostgreSQL, FastAPI or provider SDKs.

The only current external blocker is that GitHub hosted runners cannot start because the account Actions billing/spending condition is unresolved.

## 25. Ownership boundaries

NODE-12 owns:

```text
event envelope
registry
schema compatibility
routing key contract
partition/order contract
delivery semantic promise
producer/consumer correctness model
```

It does not own:

```text
RabbitMQ deployment topology
outbox polling worker
retry timers
DLQ operational UI
realtime WebSocket/SSE
LangGraph execution
business consumer handlers
```

Those belong to later infrastructure/execution Nodes.
