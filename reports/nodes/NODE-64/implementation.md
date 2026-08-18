# NODE-64 — Admin & Operations Console — Implementation Report

Status: **CORE_IMPLEMENTED / VALIDATING / NOT COMPLETE**  
Canonical spec: `docs/nodes/NODE-64-ADMIN-CONSOLE.md`  
Stack base: `feat/node-63-billing`

## Implemented in this node

### Independent platform-admin control plane

- Added `PlatformAdminRole`: `SUPPORT_READ`, `OPS`, `BILLING_ADMIN`, `AI_CONFIG_ADMIN`, `SECURITY_ADMIN`, `SUPER_ADMIN`.
- Organization roles do not grant platform-admin permissions.
- Requests first establish a real user identity using the existing authentication transport, then resolve an independent `platform_admin_principals` record.
- API tokens and service principals cannot enter the platform-admin browser control plane.
- High-risk permissions remain split (`queue.manage`, `provider.manage`, `registry.promote`, `security.breakglass`, etc.).

### Durable admin data

Migration `20260818_0024` adds:

- `platform_admin_principals`;
- append-only `platform_admin_audit_events`;
- scoped/expiring `platform_feature_flags`;
- append-only `platform_break_glass_grants`.

Database triggers reject UPDATE/DELETE on admin audit and break-glass evidence.

### Safe operational projections

The admin repository exposes metadata projections for:

- active/failing run counts;
- failing Run metadata;
- task failure count;
- queue depth and open DLQ count;
- DLQ failure metadata without `payload_json`;
- provider health plus latest override state;
- pending Billing webhook count;
- provider-cost 24h aggregate from the NODE-27 Cost Ledger;
- active feature flags.

The Admin repository reads provider cost but never writes Cost Ledger facts.

### Operational actions

- DLQ replay uses a stable `admin-dlq-replay:<dead_letter_id>` replay key and requires `queue.manage`.
- DLQ discard requires `queue.manage` and a reason.
- Provider health override actions reuse the existing provider-health override audit table.
- `force_disabled` and `clear_override` require `provider.manage`; lower-risk operational actions can use `provider.ops`.
- Feature flags require explicit owner, reason, scope and optional future expiry.
- Ordinary feature-flag operations cannot create or mutate a `security_locked` safety control.
- Break-glass requires `security.breakglass`, reason, target, scope and a TTL capped at 30 minutes.
- Registry production promotion is deliberately fail-closed until release-gate evidence is composed.

### Admin Web application

`apps/admin` is no longer a scaffold. The UI now provides:

- authenticated platform-admin principal/permission view;
- operations dashboard;
- failing Run inspector using safe metadata only;
- DLQ list with permission-aware replay/discard actions;
- Provider health cards with permission-aware override controls;
- scoped feature-flag list;
- explicit fail-closed Registry promotion state;
- runtime response parsing before rendering;
- CSRF header propagation for unsafe browser requests.

The organization ID currently shown in the Admin UI is an **authentication context only**. It does not grant platform-admin privileges.

## Security properties

- Organization OWNER is not a platform administrator.
- List/read paths do not return full user prompts, run input/output payloads, private artifact bytes or DLQ payloads.
- Mutations require server-side permissions and reasons; the UI permission check is only a usability projection.
- Audit and break-glass evidence is append-only at the database layer.
- Registry promotion fails closed rather than accepting an unverified version.
- Cost facts and Billing/customer revenue remain separate domains.

## Validation added

- `apps/api/tests/test_admin_node64.py`
  - platform admin vs organization roles;
  - permission matrix;
  - DLQ replay permission/audit/idempotency key;
  - Provider disable permission split;
  - release-gate fail-closed behavior;
  - break-glass TTL/audit;
  - feature-flag safety rules;
  - no private payload projection checks.
- `apps/admin/src/lib/admin/types.test.ts`
  - strict role parsing;
  - invalid dashboard metrics;
  - DLQ payload minimization;
  - Provider health score bounds.
- `tools/node64/validate_admin.py`
  - static acceptance assertions for migration, RBAC, Cost read-only projection, CSRF, safe UI and fail-closed registry behavior.

## Open gaps

Authoritative machine-readable status is in `reports/nodes/NODE-64/gap-ledger.json`.

P0 remains open for:

1. production `platform_admin_service_factory` composition;
2. production DLQ replay adapter through existing inbox/idempotency semantics;
3. production release-gate evidence adapter for registry promotion;
4. dedicated global-admin authentication/bootstrap transport and audited first-admin provisioning.

P1 remains open for the broader Organization/User/Project support explorer and searchable Admin Audit/Incident pages.

NODE-64 must remain **NOT COMPLETE** until the P0 gaps and hosted validation are closed.
