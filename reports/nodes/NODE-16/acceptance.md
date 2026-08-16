# NODE-16 Acceptance — Authentication & Tenant Isolation V1

Status: **IMPLEMENTED / VALIDATING**

## Contract and runtime implementation

- [x] Frozen organization roles: OWNER / ADMIN / EDITOR / VIEWER / BILLING.
- [x] Frozen workspace roles: ADMIN / EDITOR / VIEWER.
- [x] Central Permission registry and AccessPolicyService; handlers do not own role comparisons.
- [x] Last-owner invariant.
- [x] Email/password registration and generic login failure contract.
- [x] Production password adapter boundary is Argon2id-only and delegates cryptography to argon2-cffi.
- [x] Unknown-user login still performs password-hash verification against a dummy encoded hash.
- [x] Opaque random browser session; persistence/reference store retains only SHA-256 lookup key.
- [x] Session expiry, logout, all-session revocation and independent recent-auth window.
- [x] HttpOnly browser session cookie; non-HttpOnly CSRF cookie; SameSite=Lax; Secure outside local/dev/test.
- [x] Mutating cookie-authenticated requests require allowed Origin + CSRF cookie/header match.
- [x] Organization membership and workspace membership contract.
- [x] Invite creation, hash-only storage, revoke, exact user/email binding, expiry and replay rejection.
- [x] Email-verification one-time token and replay rejection.
- [x] Password reset hash-only token, single use and session revocation.
- [x] Authenticated password change and session revocation.
- [x] Scoped API token, plaintext returned once, hash-only persistence, scope non-escalation, tenant binding and revoke.
- [x] RequestContext carries request/trace/actor/organization/workspace/roles/permissions.
- [x] Existing business `/api/v1` router mounted behind a single authentication/tenant/permission guard.
- [x] Cross-tenant selection returns the same not-found category used for unavailable tenant resources.
- [x] Domain Repository Protocols require `organization_id` on all current get/save/append methods.
- [x] NODE-10 `tenant_session()` and PostgreSQL RLS boundary retained and explicitly validated.
- [x] Pre-tenant auth security audit separated from tenant-only `audit_events`.
- [x] Login/reset/invite-accept rate-limit reference implementation.

## HTTP contract

- [x] `POST /api/v1/auth/register`.
- [x] `POST /api/v1/auth/login`.
- [x] `POST /api/v1/auth/logout`.
- [x] `GET /api/v1/auth/me`.
- [x] Auth response schemas do not contain password/session/API-token secret fields.
- [x] NODE-11 REST tests explicitly isolate their historical contract by overriding only the NODE-16 guard.
- [x] Separate NODE-16 HTTP/business-guard integration suites exercise the real security boundary.

## PostgreSQL forward migration

- [x] New forward migration `20260816_0002`, based on `20260816_0001`; NODE-10 SQL snapshot not rewritten.
- [x] `users.email_verified_at` and `users.disabled_at`.
- [x] Organization role constraint aligned to owner/admin/editor/viewer/billing.
- [x] `password_credentials` with Argon2id encoded-hash CHECK.
- [x] `auth_sessions` with SHA-256 session lookup CHECK.
- [x] `auth_one_time_tokens` for invite/password-reset/email-verification.
- [x] `api_tokens` with organization RLS.
- [x] `auth_security_events` supports pre-tenant events and is append-only for `lumi_app`.
- [x] `lumi_app` receives explicit minimum runtime privileges on new auth tables.
- [x] Downgrade removes NODE-16 additions and restores NODE-10 role constraint.
- [x] NODE-10 schema validator made forward-compatible while keeping the frozen 0001 SQL snapshot exact.
- [x] NODE-10 database runner now discovers current Alembic head rather than hard-coding 0001.

## Executable evidence committed

The branch contains:

- auth/session/RBAC/tenant unit and adversarial tests;
- FastAPI register/login/me/logout integration tests;
- business-router authentication/permission/CSRF/cross-tenant tests;
- verification/revoke/recent-auth/password-change security tests;
- static architecture validator (`tools/node16/validate_auth_tenant.py`);
- 10 machine-readable auth JSON Schema exports;
- PostgreSQL auth/RLS/hash/append-only/role-constraint integration test;
- migration upgrade → downgrade-to-0001 → reapply workflow.

These executable assets are **committed but not yet claimed PASS** in this acceptance record. No canonical Python 3.12 or PostgreSQL hosted execution has occurred for this branch at the time this file is written.

## Explicit remaining gaps

Authoritative file: `reports/nodes/NODE-16/gap-ledger.json`.

1. `AUTH-DEP-001` — `argon2-cffi` is not yet part of the frozen workspace lock. The production adapter fails closed when absent. Test doubles are not production crypto evidence.
2. `AUTH-PERSIST-002` — reference AuthService uses MemoryAuthStore; transactional PostgreSQL AuthStore wiring remains.
3. `AUTH-MAIL-003` — invite/email-verification mail delivery adapter remains to be wired to Mailpit/production provider.
4. `AUTH-CI-004` — hosted runner/PostgreSQL execution is expected to remain externally blocked until the repository/account Actions billing or spending-limit condition is corrected.

## Conditions before COMPLETE

Do not mark NODE-16 COMPLETE until all of the following are true:

1. the production Argon2 dependency is reviewed, pinned and regenerated into the frozen workspace lock;
2. canonical Python 3.12 auth/unit/HTTP tests pass;
3. Ruff and Pyright pass for NODE-16 scope;
4. 10 exported JSON Schemas generate and parse;
5. PostgreSQL upgrades from 0001 to 0002 successfully;
6. baseline NODE-10 invariants still pass at current head;
7. NODE-16 auth DB tests pass, including API-token RLS and append-only security audit;
8. downgrade to 0001 removes NODE-16 schema while preserving baseline, then reapply succeeds;
9. SQL AuthStore runtime adapter is wired and exercised;
10. repository CI/security gates execute green;
11. upstream stacked dependencies are resolved in order.

No production mail delivery, live OAuth/OIDC, MFA, SAML/SCIM, or production deployment PASS is claimed by NODE-16.

Next engineering node after acceptance: **NODE-17 — Project Core**.
