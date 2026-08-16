# NODE-19 Persistence Mapping V1

## Baseline

NODE-10 already created tenant-scoped `outbox_events` and `inbox_events`. NODE-19 keeps those historical definitions and extends them only through migration `20260816_0005`.

## Outbox extension

Added fields:

```text
last_publish_attempt_at TIMESTAMPTZ NULL
next_publish_at         TIMESTAMPTZ NULL
last_publish_error      TEXT NULL
```

`published_at` remains the durable completion marker. `publish_attempts` remains monotonic.

The due index is scoped by organization because the dispatcher operates inside NODE-16 RLS rather than bypassing it.

## Runtime jobs

`runtime_jobs` stores:

- tenant/project identity;
- job kind;
- operation/resource references;
- durable state;
- attempt counters;
- cancellation timestamp;
- retry due timestamp;
- safe small input/output JSON;
- traceparent;
- bounded error metadata;
- timestamps and optimistic version.

It does not store file bodies, provider secrets, presigned URLs, or arbitrary credentials.

A security-definer trigger rejects a Project whose organization does not equal the row organization. RLS then restricts all application reads/writes to `app.current_organization_id`.

## Inbox

Identity remains:

```text
(event_id, consumer)
```

A production handler must use the same database connection/transaction passed by `PostgresInboxStore` when mutating business state. If it opens a second independent transaction, the effectively-once guarantee does not apply.

## Dead letters

`dead_letter_records` is tenant-owned and RLS-protected. It stores original message identity/payload plus source queue/exchange/routing key, error classification, attempts and replay status.

Malformed messages without a trustworthy tenant identity are not inserted into this table; they go to broker quarantine/DLX.

## Application permissions

`lumi_app` receives SELECT/INSERT/UPDATE on NODE-19 runtime tables and no DELETE. Destructive retention/GC remains an operator/background responsibility with separate privilege.

## Forward-only rule

NODE-19 does not edit migrations `0001` through `0004`. Rollback target is exactly `20260816_0004`; reapplying `0005` must recreate the same runtime contract.
