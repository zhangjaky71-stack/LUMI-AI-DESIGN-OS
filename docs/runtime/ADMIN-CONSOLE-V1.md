# Admin Console Runtime V1

Status: **IMPLEMENTED / VALIDATING / NOT COMPLETE**

## Security boundary

Platform Admin is a separate principal from tenant Organization roles. `OWNER` or tenant `ADMIN` never implies platform privileges. The runtime resolves a `PlatformAdminActor` with dedicated roles and permissions before any `/admin/*` operation.

## Read surfaces

The console projects safe operational views for users/organizations, runs/tasks, provider health/circuit/routing/pricing snapshot, queue/DLQ, Agent/Skill registry, customer billing references and audit events. PII is masked by default and provider/queue content is represented by opaque refs/codes rather than arbitrary sensitive payloads.

## Privileged writes

Sensitive writes carry an exact action summary, exact impact scope, reason, ticket/reference and `CONFIRM` second confirmation. Server-side services recompute the expected summary/scope and reject stale or mismatched confirmation.

- run retry/cancel goes through RunOpsPort;
- provider disable goes through ProviderOpsPort, is temporary and capped at 24 hours;
- queue requeue goes through QueueOpsPort and CAS-checks the original immutable payload ref + SHA-256;
- Agent/Skill enable/disable goes through RegistryOpsPort;
- Billing correction goes through `Node63CreditLedgerAdapter` and appends NODE-63 `ADJUSTMENT` entries; balance is never assigned directly;
- PII reveal and View-as emit structured admin audit events.

There is no arbitrary SQL console, process-kill primitive, queue payload editor or direct payment-provider state mutation API.

## View-as

V1 View-as is support-safe only: readonly, target-scoped, at most 15 minutes and audited on start/end. It is not true impersonation and exposes no write path.

## Audit boundary

NODE-64 uses `AdminAuditSink` and does not silently drop privileged events. The deterministic in-memory sink is test evidence only. NODE-65 owns durable append-only audit persistence, export/retention and production transaction integration. Until NODE-65 is bound, production privileged writes remain an explicit integration gate.

## Production adapters still required

- platform admin identity/role resolver and step-up authentication;
- Support Directory across real tenant data;
- Run/Task operation adapters;
- Provider Health / Model Router control adapter;
- Queue/DLQ runtime adapter with immutable payload identity;
- Agent Registry and Skill Registry control adapters;
- NODE-27 actual provider-cost projection;
- NODE-63 durable BillingRepository transaction adapter;
- NODE-65 durable Audit & Governance sink;
- stronger dual-control policy for production-wide/provider-impacting actions.
