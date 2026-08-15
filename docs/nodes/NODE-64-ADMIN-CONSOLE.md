# NODE-64 — Admin Console

> Phase: 8 SaaS & Collaboration  
> Status: **IMPLEMENTED / VALIDATING / NOT COMPLETE**  
> Priority: P1 / OPERATIONS  
> Depends on: NODE-16, NODE-19, NODE-24, NODE-27, NODE-30, NODE-31, NODE-63  
> Produces: Platform Admin principal、safe operations service ports、Admin API、internal operations console

## 1. Goal

Provide an internal LUMI operations console without turning support access into a privileged backdoor. Platform Admin is explicitly separate from customer Organization roles and dangerous operations must pass permission, service, confirmation and audit boundaries.

## 2. Platform roles and permissions

Implemented roles:
- SUPPORT_READ
- SUPPORT_WRITE_LIMITED
- BILLING_ADMIN
- OPS
- MODEL_ADMIN
- SECURITY_AUDITOR
- PRIVACY_ADMIN

Canonical permissions include `admin.user.read`, `admin.user.manage_limited`, `admin.billing.read`, `admin.billing.adjust`, `admin.provider.read`, `admin.provider.manage`, `admin.queue.read`, `admin.queue.requeue`, `admin.agent_registry.manage`, `admin.skill_registry.manage`, `admin.audit.read`, `admin.privacy.execute`.

A tenant `OWNER` / `ADMIN` does not imply any of these permissions. The App Shell exposes `/app/admin` only when a separately resolved `platform_admin` principal exists; API authorization remains authoritative.

## 3. Product surface

`/app/admin` implements:
- Overview: active users/orgs, daily generations, failure rate, provider health, queue depth, cost today, critical alerts;
- Users & Organizations: masked support-safe identity, memberships, recent error codes, explicit PII reveal, readonly View-as;
- Runs: run/task state, provider/tool/error/cost and guarded retry;
- Providers: health, circuit, synthetic health, routing weight, pricing snapshot and temporary disable;
- Queue: state/DLQ, attempts, immutable payload ref/hash and original-payload requeue;
- Registry: Agent/Skill version, traffic, readonly deploy diff and guarded enable/disable through registry service;
- Billing: customer billing support with immutable NODE-63 credit adjustments;
- Audit: safe event projection; durable NODE-65 integration remains pending.

## 4. Privileged action contract

Sensitive action confirmation includes exact action summary, exact impact scope, reason, ticket/reference and literal `CONFIRM`. The server recomputes expected summary and scope to reject stale confirmation.

Provider disable is limited to a future expiry no more than 24 hours. Queue requeue passes the pre-existing payload ref and SHA-256 as compare-and-set expectations; there is no payload editor.

## 5. PII and View-as

Email and phone are masked by default. Full reveal requires `admin.privacy.execute`, reason and ticket, and emits an audit event without copying revealed values into audit metadata.

View-as is readonly, target organization scoped, max 15 minutes and audited at start/end. V1 exposes no mutation route while View-as is active.

## 6. Billing safety

`Node63CreditLedgerAdapter` appends an immutable `ADJUSTMENT` entry using NODE-63 `BillingRepository.append_credit`. Negative adjustments use the same non-negative balance guard. No admin API can assign a credit balance or mutate arbitrary payment-provider subscription/invoice state.

## 7. Audit handoff

All admin writes, PII reveal and View-as emit structured `AdminAuditEvent` records to `AdminAuditSink`. The in-memory sink is deterministic test evidence only. NODE-65 owns the durable append-only Audit & Governance implementation; production write enablement is gated on that sink.

## 8. API

- `GET /admin/console`
- `GET /admin/users`
- `POST /admin/users/{id}:reveal-pii`
- `POST /admin/users/{id}:view-as`
- `POST /admin/view-as/{id}:end`
- `GET /admin/runs`
- `POST /admin/runs/{id}:retry`
- `POST /admin/runs/{id}:cancel`
- `GET /admin/providers`
- `POST /admin/providers/{id}:disable`
- `GET /admin/queue`
- `POST /admin/queue/{id}:requeue`
- `GET /admin/registry`
- `POST /admin/registry/{kind}/{id}:set-enabled`
- `GET /admin/billing/{organization_id}`
- `POST /admin/billing/{organization_id}:adjust`
- `GET /admin/audit`

No endpoint accepts arbitrary SQL, process identifiers for kill, editable queue payloads or provider payment-state patches.

## 9. Validation staged

- platform RBAC and tenant-role separation;
- PII masking/reveal authorization;
- provider disable second confirmation + bounded expiry;
- queue immutable payload CAS;
- NODE-63 ADJUSTMENT ledger integration and non-negative guard;
- View-as readonly/ownership/TTL;
- admin write audit events;
- FastAPI route and permission tests;
- frontend contract/gateway tests;
- product browser E2E and mobile;
- production deterministic-fixture leakage scan;
- prior NODE-63 through NODE-54 regressions.

## 10. Production integration gates

1. NODE-16 production platform-admin identity, role and step-up resolver;
2. production Support Directory, Run/Task, Provider, Queue and Registry adapters;
3. NODE-27 real provider cost projection;
4. NODE-63 durable BillingRepository adapter;
5. NODE-65 durable Audit & Governance pipeline;
6. production-wide/provider-impacting dual-control / stronger verification;
7. hosted pinned validation observed green.

## 11. Acceptance

- [x] major operational domains represented through safe service ports;
- [x] dangerous actions avoid SQL/process escape hatches;
- [x] platform admin separated from tenant role;
- [x] sensitive actions emit structured audit events;
- [x] PII masked by default and explicit reveal audited;
- [x] Billing adjustment uses immutable NODE-63 ledger;
- [x] Queue requeue preserves immutable payload identity;
- [x] readonly View-as implemented;
- [x] tests/API/web gates staged;
- [ ] production adapters connected;
- [ ] NODE-65 durable audit bound;
- [ ] hosted pinned validation green.

## 12. Definition of Done

```text
admin console implemented
+ privileged workflow tests observed green
+ production service adapters connected
+ durable audit integration ready
```

Next: **NODE-65 — Audit & Governance**.
