# NODE-12 — Acceptance Evidence

> Status: **VALIDATING**  
> Branch: `feat/node-12-event-contract`  
> Stacked Base: `feat/node-11-api-contract` / PR #77  
> Node: Event / Message Contract  
> Date: 2026-08-16

## Scope implemented

NODE-12 freezes a broker-neutral asynchronous fact contract on top of the NODE-10 Outbox/Inbox persistence boundary.

Implemented:

- immutable strict `EventEnvelope[T]`;
- UUIDv7 event identity;
- timezone-aware historical occurrence time;
- tenant, aggregate and aggregate-version identity;
- producer, correlation, causation and trace context;
- stable aggregate-local partition key;
- nine frozen P0 event payload types and registry;
- strict versioned event type naming;
- Decimal-safe cost-event serialization;
- Outbox projection preserving the full canonical envelope;
- Inbox consumer dedupe identity `(event_id, consumer)`;
- replay rule preserving historical `event_id` and `occurred_at`;
- explicit at-least-once delivery semantics;
- explicit no-global-order rule;
- payload-minimization/privacy rules;
- broker/ORM/LangGraph/provider dependency-purity test;
- deterministic event architecture validator;
- dedicated frozen-install contract workflow.

Canonical documentation:

```text
docs/events/EVENT-CONTRACT-V1.md
```

## Frozen P0 registry

```text
lumi.project.created.v1
lumi.asset.ready.v1
lumi.agent_run.started.v1
lumi.agent_run.waiting_user.v1
lumi.task.succeeded.v1
lumi.generation.completed.v1
lumi.artifact.version_created.v1
lumi.artifact.approved.v1
lumi.cost.recorded.v1
```

Each type maps to one strict immutable Pydantic payload model. The registry rejects unknown majors rather than guessing compatibility.

## Delivery semantics

V1 is deliberately:

```text
at-least-once delivery
+ transactional Outbox producer
+ durable Inbox consumer dedupe
+ idempotent consumer effect
```

No exactly-once transport claim is made.

A replay preserves the original event identity/time. Intentional reprocessing uses a new consumer identity/replay namespace instead of fabricating a fresh event ID for an old fact.

## Ordering

There is no global event order.

Stable aggregate-local partition key:

```text
org:<organization_id>:aggregate:<aggregate_type>:<aggregate_id>
```

`aggregate_version`, when available, is the source aggregate sequence signal. UUIDv7 timestamp order is never used as a substitute for business causality.

## Outbox / Inbox alignment

Producer projection keeps:

```text
event_id
organization_id
event_type
aggregate_type
aggregate_id
occurred_at
partition_key
full envelope_json
```

This maps onto NODE-10 `outbox_events` without importing SQLAlchemy into the event contract package.

Consumer receipt identity maps conceptually onto:

```text
inbox_events(event_id, consumer)
```

The event package owns semantics only; persistence/transport adapters implement storage and acknowledgement behavior.

## Executable tests

`apps/api/tests/test_event_contract.py` covers:

1. UUIDv7 event factory + timezone-aware occurrence time;
2. immutable envelope and `extra=forbid` behavior;
3. versioned event-type syntax;
4. exact nine-type registry and round trip;
5. stable aggregate-local partition key;
6. Decimal cost serialization as a JSON string, never float;
7. full Outbox projection identity/payload preservation;
8. Inbox consumer receipt identity;
9. replay preserving event ID/time;
10. naive timestamp rejection;
11. broker/ORM/LangGraph/provider import purity.

`tools/node12/validate_event_contract.py` additionally checks registry completeness, strict/frozen payload configuration, round-trip serialization, Outbox projection, Decimal safety, dependency purity and documented delivery/replay/ordering semantics.

## Architecture boundary

`lumi_api.events` must not import:

```text
SQLAlchemy / asyncpg / Alembic
Kafka / NATS / Redis / Celery
LangGraph / LangChain
OpenAI / Anthropic
object-storage SDKs
```

Later broker/worker/realtime adapters depend on this contract. The contract does not depend on them.

## Validation status

Local code has been implemented and static/executable validation is committed, but repository-hosted execution is still required.

The repository has an active account-level GitHub Actions billing/spending-limit condition on preceding stacked PRs. NODE-12 will record its own PR run after creation; no result is inherited from another node.

## Acceptance checklist

- [x] immutable broker-neutral envelope implemented.
- [x] UUIDv7 identity / tenant / aggregate / causal metadata implemented.
- [x] nine P0 v1 event payloads and registry implemented.
- [x] Decimal-safe cost serialization contract implemented.
- [x] transactional Outbox projection implemented without ORM coupling.
- [x] Inbox consumer identity implemented.
- [x] at-least-once delivery/idempotency semantics documented.
- [x] replay preserves event ID/time.
- [x] aggregate-local ordering / no-global-order semantics documented.
- [x] broker/ORM/orchestration/provider dependency-purity tests committed.
- [x] dedicated NODE-12 validator/workflow committed.
- [ ] repository frozen install passes.
- [ ] NODE-12 validator passes on Python 3.12.
- [ ] event pytest passes on Python 3.12.
- [ ] repository CI/security gates pass.
- [ ] stacked NODE-09/10/11 dependencies resolve and merge.
- [ ] NODE-12 merged and NODE index updated to COMPLETE.

NODE-12 remains `VALIDATING`, not `COMPLETE`.
