# Provider Health Persistence Mapping V1

Status: **NODE-24 FROZEN**

## 1. Storage split

Provider Health intentionally uses two persistence classes:

| Store | Purpose | Correctness role |
|---|---|---|
| Redis | rolling observations, circuit state, recovery-probe counters, short-lived manual override | soft operational state only |
| PostgreSQL | periodic summary history and manual override audit | durable operational evidence |

Capability, pricing and benchmark truth remains in NODE-23. Paid-side-effect identity remains in NODE-20. Cost Ledger truth remains outside Provider Health.

## 2. Redis keys

`RedisHealthStateStore` uses a configured prefix (default `lumi:provider-health:v1`) plus hashed scope identifiers. Raw prompts, outputs and secrets never enter keys.

Logical scopes:

```text
provider | <provider> | * | *
endpoint | <provider> | <model> | <capability-or-*>
```

The logical scope is SHA-256 truncated before being appended to the Redis key. Manual override keys use a distinct override namespace.

Every state has TTL. `ProviderHealthPolicy` rejects a state TTL shorter than either the rolling window or OPEN cooldown.

Per-key distributed Redis locks serialize read/modify/write transitions and recovery-probe admission across replicas. If Redis access fails, callers receive operational `UNKNOWN`; no business transaction is rolled back or reconstructed from Redis.

## 3. PostgreSQL migration 0008

Migration:

```text
20260816_0007
      ↓
20260816_0008
```

NODE-24 never rewrites migrations 0001–0007.

### provider_health_summaries

Append-only-by-grant history with:

- UUID id;
- provider/model/capability scope;
- six-state health value;
- score and sample count;
- success/failure/429/timeout rates;
- latency P50/P95;
- queue completion P95;
- consecutive failures;
- observed timestamp;
- optional source instance;
- creation timestamp.

The application role receives SELECT/INSERT and no UPDATE/DELETE.

### provider_health_override_audit

Durable audit with:

- UUID id;
- action (`force_disabled`, `force_degraded`, `clear_override`, `clear_breaker`);
- provider/model/capability scope;
- actor id;
- explicit reason;
- observed timestamp;
- optional expiry;
- creation timestamp.

The application role receives SELECT/INSERT only. In addition, database trigger `trg_provider_health_override_audit_immutable` rejects UPDATE or DELETE regardless of application mistakes.

## 4. Runtime adapters

`PostgresProviderHealthPersistence` is asyncpg-compatible but imports no database driver. It accepts a connection implementing an async `execute()` boundary and only appends rows.

`RedisHealthStateStore` is redis-py compatible but imports no Redis client package. Client authentication, TLS, credentials, connection pooling and lifecycle belong to service bootstrap.

This keeps the reusable Model Gateway domain package dependency-light while allowing real Redis/PostgreSQL verification in CI.

## 5. Manual override ordering

Production Admin orchestration must use this ordering:

```text
validate authenticated operator + authorization
→ append durable provider_health_override_audit row
→ apply short-lived Redis override
→ return audit id / operational result
```

If durable audit append fails, the override must not be applied. If Redis apply fails after audit append, the durable audit remains evidence of the attempted action and the API must report operational failure; no unaudited retry should silently mutate state.

The NODE-24 core supplies both persistence and runtime contracts. Authenticated Admin API/UI composition remains `HEALTH-ADMIN-003`.

## 6. Downgrade

`20260816_0008 -> 20260816_0007` drops only NODE-24 trigger/function/tables. NODE-23 registry tables and all earlier runtime data remain intact.

The NODE-24 workflow is designed to prove:

```text
0007 → 0008
DB invariants
0008 → 0007
NODE-23 tables preserved + NODE-24 tables removed
0007 → 0008
DB invariants again
```

## 7. Retention

Redis TTL is operational and policy-controlled. PostgreSQL health-summary/audit retention is not physically deleted by NODE-24. Audit retention/legal policy and historical summary compaction require an explicit later operational policy; NODE-24 does not introduce destructive cleanup behind the append-only contract.
