# LUMI Authentication & Tenant Isolation V1

Status: **FROZEN CONTRACT / NODE-16**  
Depends on: NODE-10 Database Baseline, NODE-11 API Contract

## 1. Security boundary

`X-Organization-ID` is a tenant selector, not proof of access. A request is authorized only after:

```text
session/API token authentication
→ resolve Principal
→ verify selected organization belongs to Principal
→ evaluate centralized Permission
→ build RequestContext
→ open tenant-scoped repository/DB session
→ PostgreSQL RLS applies app.current_organization_id
```

Absent resource IDs and cross-tenant resource IDs use the same outward `TENANT_RESOURCE_NOT_FOUND` category to reduce enumeration risk.

## 2. Identity modes

P0 supports:

- email + password;
- opaque browser sessions;
- organization/workspace membership;
- invitation;
- email-verification one-time tokens;
- password-reset one-time tokens;
- scoped API tokens.

OIDC/MFA/SAML/SCIM remain later adapters and do not weaken this contract.

## 3. Passwords

Production password hashing is Argon2id through a mature external implementation. LUMI does not implement Argon2, PBKDF, bcrypt or scrypt itself.

`Argon2idPasswordHasher` delegates to `argon2-cffi` and fails closed if the package is unavailable. Persistent password records contain only an encoded `$argon2id$...` value. Each user's salt is library-managed as part of that encoding.

Unknown-email login and wrong-password login share the same outward `INVALID_CREDENTIALS` result. A dummy Argon2 hash is verified for unknown users so the flow does not trivially skip password-hash work.

The current frozen workspace does not yet contain `argon2-cffi`; this is explicitly tracked as `AUTH-DEP-001`, not replaced with weaker test crypto.

## 4. Browser sessions

A browser receives a high-entropy opaque session secret once. Durable state stores only SHA-256 of that random secret as the lookup key.

Session records contain:

```text
session_hash
user_id
created_at
expires_at
last_seen_at
recent_auth_at
revoked_at?
user_agent_hash?
ip_risk_metadata
```

The raw User-Agent is hashed before storage. Session activity requires not revoked and `now < expires_at`. Sensitive runtime operations may call `require_recent_authentication()` independently of normal session lifetime.

Cookie policy:

```text
lumi_session: HttpOnly, Path=/, SameSite=Lax, Secure outside local/dev/test
lumi_csrf:    readable by client, Path=/, SameSite=Lax, Secure outside local/dev/test
```

Both cookies are deleted on logout. Auth responses are `Cache-Control: no-store`.

## 5. CSRF

Cookie-authenticated mutating requests require all of:

- allowed `Origin`;
- CSRF cookie;
- `X-CSRF-Token` header;
- constant-time equality of cookie/header values.

GET/HEAD/OPTIONS are exempt. Bearer API tokens are not cookie credentials and therefore do not use this CSRF mechanism. CORS is not treated as CSRF protection.

## 6. Roles and permissions

Frozen organization roles:

- `OWNER`
- `ADMIN`
- `EDITOR`
- `VIEWER`
- `BILLING`

Workspace roles remain `ADMIN / EDITOR / VIEWER`.

Frozen permission registry:

```text
project.read
project.write
asset.upload
artifact.approve
brand.manage
member.invite
member.manage
billing.read
billing.manage
admin.audit.read
api_token.manage
```

Role behavior:

- OWNER: all P0 permissions.
- ADMIN: operational/admin permissions plus billing.read, but not billing.manage.
- EDITOR: content read/write, asset upload, artifact approval.
- VIEWER: project.read only.
- BILLING: billing.read + billing.manage only.

Handlers do not make direct role comparisons. `AccessPolicyService` owns permission evaluation.

The last OWNER of an organization cannot be removed or demoted.

## 7. Organization and workspace membership

A user must have an organization membership before a workspace membership can be created. Selecting an organization for a request is valid only if the authenticated user is a member of that organization or the API token is explicitly scoped to it.

Cross-tenant IDs fail before ordinary permission evaluation where possible, avoiding a difference between “exists elsewhere” and “does not exist”.

## 8. Tenant-scoped repositories and PostgreSQL RLS

Domain Repository Protocols require `organization_id` for all current get/save/append methods. The forbidden shape is:

```python
repo.get(resource_id)
```

The frozen shape is:

```python
repo.get(organization_id, resource_id)
```

After membership authorization, NODE-10 `tenant_session()` sets transaction-local `app.current_organization_id`. Existing PostgreSQL RLS policies then enforce `organization_id = lumi_current_organization_id()` for tenant tables.

NODE-16 adds RLS to `api_tokens`; password/session/global verification tables are user/security scoped rather than normal tenant data.

## 9. RequestContext

Every authenticated business request builds:

```text
request_id
trace_id
actor_id
organization_id
workspace_id?
roles
permissions
```

The FastAPI guard writes this to `request.state.lumi_context`, allowing logs/audit/application services to consume a single trusted tenant context instead of rebuilding it manually.

## 10. HTTP contract

NODE-16 adds:

```text
POST /api/v1/auth/register
POST /api/v1/auth/login
POST /api/v1/auth/logout
GET  /api/v1/auth/me
```

The pre-existing NODE-11 business router is mounted behind one central `enforce_api_auth` dependency. For the current business surface, GET/HEAD requires `project.read`, while mutating operations require `project.write`. Later asset/brand/billing endpoint families may extend the path-to-permission resolver without bypassing the guard.

NODE-11 contract tests explicitly override this guard only to isolate NODE-11 REST/ETag/idempotency behavior; NODE-16 has separate integration tests for the real security boundary.

## 11. Invitation

Invite flow:

```text
member.invite authorization
→ random high-entropy secret
→ persist SHA-256 hash + normalized email + organization + role + expiry
→ deliver secret through mail adapter
→ accepting user ID must belong to that exact stored email
→ membership created
→ token consumed
```

Invite tokens are single-use, revocable and rate-limited. Replay and attaching the invite to a different user ID fail closed.

## 12. Email verification

Email-verification tokens use the same one-time hash-only mechanism. Consuming a valid token records `email_verified_at` and consumes the token. Replay fails.

Mail delivery is an adapter boundary. NODE-16 freezes the verification semantics but does not claim a production mail-provider integration.

## 13. Password reset and change

Password-reset requests do not reveal whether the email exists. For a known user, only a hash of the reset secret is persisted. A valid reset is short-lived and single-use, writes a new Argon2id credential and revokes existing sessions.

Authenticated password change verifies the current password, writes a fresh Argon2id credential, revokes existing sessions and emits a security audit event.

## 14. API tokens

API tokens contain a public prefix plus a random secret; the full plaintext value is returned only at creation. Persistence stores only SHA-256 of the random bearer token, along with organization, scopes, expiry/use/revocation metadata.

Token scopes must be a subset of the creating user's current permissions. API tokens cannot manufacture permissions the creator does not possess.

A token is permanently bound to one organization. Supplying another `X-Organization-ID` returns the tenant-not-found category.

## 15. Rate limiting

Login, password-reset and invite-accept flows have independent rate-limit keys. `MemoryRateLimiter` is a deterministic reference implementation; Redis can coordinate counters later. Security decisions and audit history are not delegated to Redis state.

## 16. Audit split

Organization-scoped actions can enter the existing tenant `audit_events` chain.

Some auth events occur before a tenant is known, especially a failed login for an unknown email. NODE-16 therefore adds `auth_security_events`, where organization is nullable and secrets/passwords are forbidden. This avoids inventing a tenant merely to satisfy an audit foreign key.

Reference runtime events include login success/failure category, logout, password change/reset, session revocation, invite create/accept/revoke, membership role change, and API token create/revoke.

## 17. Persistence migration

NODE-16 adds forward migration `20260816_0002` rather than modifying NODE-10 history. It adds:

- `users.email_verified_at`;
- updated organization role constraint;
- `password_credentials`;
- `auth_sessions`;
- `auth_one_time_tokens`;
- `api_tokens` + RLS;
- `auth_security_events`.

Downgrade removes NODE-16 structures and restores the original NODE-10 role constraint.

## 18. Known runtime gaps

`reports/nodes/NODE-16/gap-ledger.json` is authoritative for remaining non-hidden gaps. In particular, production Argon2 dependency locking and a transactional PostgreSQL AuthStore adapter remain open. The in-memory AuthStore is a reference runtime, not a production persistence claim.

## 19. Machine-readable schemas

`tools/node16/export_auth_schemas.py` emits 10 schemas covering User, PasswordCredential, BrowserSession, organization/workspace membership, one-time token, API token, Principal, RequestContext and AuthAuditEvent.

## 20. Security invariants

The NODE-16 gate must prove or statically enforce:

- no plaintext password/session/token persistence fields;
- Argon2id production password boundary;
- tenant-scoped repository signatures;
- role/permission matrix;
- last-owner invariant;
- generic login failure;
- session expiry/revocation;
- cookie CSRF rejection;
- invite/reset/verification replay rejection;
- API token scope non-escalation;
- cross-tenant request rejection;
- migration upgrade/downgrade/reapply design;
- existing tenant-session/RLS bridge remains present.
