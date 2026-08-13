# NODE-12 Acceptance Report

> Status: **IMPLEMENTED / VALIDATING / BLOCKED_EXTERNAL**  
> Node: **NODE-12 — Event Contract**  
> Branch: `node-12-event-contract`  
> Stack base: `node-11-api-contract`

---

## 1. Result

NODE-12 now has a language-neutral event contract and a zero-runtime-dependency Python reference implementation.

Implemented:

- closed V1 event envelope schema;
- exactly 9 NODE-09 domain event definitions;
- JSON Schema 2020-12 payload schemas;
- registry-owned type/routing/partition/subject/schema mapping;
- immutable/deep-frozen reference EventEnvelope;
- registry loader + envelope factory;
- delivery-attempt broker headers without envelope mutation;
- at-least-once delivery declaration;
- partition-scoped ordering declaration;
- transactional Outbox/Inbox producer-consumer correctness model;
- schema compatibility policy;
- secret/raw-response payload guard;
- decimal-string cost payload invariant;
- dependency-free validator;
- dependency-free stdlib tests;
- dedicated Event Contract workflow;
- reference documentation.

## 2. Frozen event vocabulary

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

NODE-12 does not add undocumented event names beyond the NODE-09 vocabulary.

## 3. Delivery contract

Declared:

```text
at_least_once
```

Not declared:

```text
exactly_once
global_order
```

Correctness strategy:

```text
business mutation + outbox in one DB transaction
→ at-least-once publish
→ consumer inbox dedupe
→ idempotent consumer effects
```

## 4. Ordering contract

Ordering scope:

```text
partitionkey
```

Every registry entry names a required payload `partition_field`; envelope factory constructs the stable partition key from it.

Consumers may not infer global ordering from timestamps.

## 5. Envelope contract

Required top-level attributes:

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

Top-level `additionalProperties=false` prevents producer-specific envelope drift.

## 6. Payload compatibility

Payload schemas use:

```text
additionalProperties=true
```

so additive optional fields remain consumer-compatible.

Breaking changes require schema-version evolution.

## 7. Financial precision

`cost.recorded.amount` is represented as a decimal string rather than JSON floating point.

The validator explicitly rejects changing it to a JSON number.

## 8. Sensitive-data guard

The contract validator rejects payload property names matching secret/raw patterns such as:

```text
api_key
secret
password
authorization
access_token
refresh_token
raw_response
```

Binary/media data and provider raw responses are not part of event payload contracts.

## 9. Reference runtime

`services/event-contract` has no runtime dependencies.

Reference functions:

```text
load_registry
validate_payload
build_envelope
broker_headers
```

Envelope data is deep-frozen after construction.

## 10. Retry immutability

Delivery attempts are represented in broker headers:

```text
x-lumi-delivery-attempt
```

Changing retry attempt does not change serialized envelope/event ID.

## 11. Registry validation

`scripts/validate_event_contracts.py` verifies:

- exact frozen vocabulary;
- unique type/routing key;
- owner bounded context;
- canonical payload path;
- JSON Schema `$id` and draft;
- partition field required;
- subject template only references required facts;
- payload additive compatibility;
- forbidden secret/raw fields;
- decimal-string cost amount;
- at-least-once delivery;
- partition ordering.

## 12. Stdlib test suite

`services/event-contract/tests/test_event_contract.py` covers:

- registry/vocabulary;
- payload schema IDs;
- envelope build/round-trip;
- deep immutable payload;
- required payload rejection;
- retry metadata without envelope mutation;
- closed top-level envelope schema.

## 13. CI independence

`.github/workflows/event-contract.yml` deliberately requires only:

```text
Git checkout
Python 3.12
```

It does not require:

```text
uv.lock
PostgreSQL
FastAPI
SQLAlchemy
RabbitMQ runtime
provider SDKs
```

This allows event-contract correctness to be isolated from application dependency failures.

## 14. External blocker

GitHub hosted runners are currently unable to start because GitHub reports a Billing & plans / Actions spending condition:

```text
The job was not started because recent account payments have failed
or your spending limit needs to be increased.
```

Therefore the new dependency-free Event Contract workflow has not received a real hosted Python execution yet.

This is `BLOCKED_EXTERNAL`, not a test failure.

## 15. Completion gate

NODE-12 may be marked COMPLETE only after:

```text
GitHub Actions billing/spending fixed
+ Event Contract workflow starts on a real runner
+ compileall PASS
+ validate_event_contracts.py PASS
+ stdlib unittest PASS
+ stacked upstream contract/security gates remain consistent
```

Until then:

**NODE-12 engineering status: IMPLEMENTED / VALIDATING / BLOCKED_EXTERNAL.**
