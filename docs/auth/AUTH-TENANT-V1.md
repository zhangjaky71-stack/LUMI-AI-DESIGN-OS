# LUMI Authentication & Tenant V1

> Official node: **NODE-16 — Authentication & Tenant**  
> Status: **IMPLEMENTED / VALIDATING / BLOCKED_EXTERNAL**  
> Depends on: NODE-10 Database Schema, NODE-11 API Contract, NODE-15 Phase-1 contracts

## 1. Security boundary

LUMI V1 authentication uses:

```text
local email + password
server-side opaque session
Secure / HttpOnly / SameSite cookie
CSRF token + Origin validation for browser mutations
organization membership + RBAC
object-level tenant guard
single-use hashed verification/reset/invite tokens
scoped opaque API tokens
```

OIDC/SSO remains P1. LUMI does not implement partial/custom OAuth crypto in NODE-16.

## 2. Passwords

Password hashing uses the mature `argon2-cffi` adapter with Argon2id. LUMI does not implement custom password cryptography.

Database stores only:

```text
$argon2id$... password hash
changed_at
version
```

No plaintext password or reversible encryption exists in the schema.

The adapter supports verification and `check_needs_rehash()` so password parameters may be upgraded after successful login without changing the API contract.

## 3. Registration

Local registration transaction creates:

```text
User
PasswordCredential
Organization
OWNER OrganizationMember
Default Workspace
EmailVerificationToken(hash only)
AuditEvent
```

The verification token plaintext exists only long enough to hand to `AuthNotificationPort`; the database stores SHA-256 only.

Duplicate email/slug outward behavior is deliberately generic. The HTTP registration endpoint returns an accepted-style result instead of exposing whether an account exists.

## 4. Email verification

Email verification tokens are:

```text
opaque random secret
>= 192 bits entropy (default 256-bit source entropy)
SHA-256 hash at rest
expiry bounded
single-use
revocable
```

Replay after consumption is rejected.

## 5. Login

Login:

```text
rate limit
normalize email
load User + PasswordCredential
verify Argon2id
select active organization membership
rehash password if policy changed
issue opaque session secret + opaque CSRF secret
store only hashes
return CSRF token to browser
set session secret in HttpOnly cookie
```

Missing account, bad password, inactive account and missing active membership use the same outward credential failure class.

A dummy Argon2 verification path is used for missing accounts to reduce obvious account-existence timing differences. Production tuning may cache this process-wide; security semantics do not rely on exact timing equality.

## 6. Session

Session database state contains:

```text
user_id
active organization_id
session token hash
CSRF token hash
expires_at
last_seen_at
revoked_at
user-agent hash
risk metadata
```

The legacy boolean `revoked` remains temporarily for migration compatibility; `revoked_at` is the V1 semantic revocation source.

Browser cookie contract:

```text
name = lumi_session
HttpOnly = true
Secure = true outside local development/test
SameSite = Lax
Path = /
```

## 7. CSRF

Cookie-authenticated mutation endpoints require:

```text
X-CSRF-Token
Origin
```

The server verifies:

- Origin normalizes to scheme + authority and exactly matches an allowed origin;
- submitted CSRF token hash matches session state using constant-time comparison.

An attacker-controlled Origin or token fails before the mutation is committed.

## 8. Logout

Logout validates the server-side session and CSRF evidence, sets `revoked_at`, maintains the legacy revoked compatibility bit and expires the browser cookie.

A revoked session cannot be resolved into a principal again.

## 9. Password reset

Password reset request is enumeration-safe:

```text
existing account -> create hashed single-use reset token + notify
missing account  -> no token
HTTP response    -> same accepted response
```

Reset confirmation:

```text
validate single-use token
Argon2id-hash new password
increment credential version
mark token consumed
revoke every active session for the user
```

Old password and old sessions cease to authorize after successful reset.

## 10. Tenant model

Primary hierarchy:

```text
User
  -> OrganizationMember
Organization
  -> Workspace
  -> Project
```

`organization_id` is both data-ownership boundary and policy input.

A client-provided organization selector never grants access. Session/API-token principal resolution revalidates membership or token scope before building `RequestContext`.

## 11. RBAC V1

Frozen organization roles:

```text
OWNER
ADMIN
EDITOR
VIEWER
BILLING
```

Representative permissions:

```text
project.read
project.write
asset.upload
artifact.approve
brand.manage
member.invite
api_token.manage
billing.read
billing.manage
admin.audit.read
```

The policy core exposes a deterministic role-permission matrix. Object access checks tenant equality before permission, preventing a valid role in Org A from authorizing an Org B object.

## 12. Legacy role normalization

`0005_auth_role_hardening` normalizes any legacy lowercase organization roles to uppercase and then adds a database CHECK constraint for the frozen V1 vocabulary.

This avoids runtime case guessing and makes invalid historical roles visible during migration instead of silently granting unexpected authority.

## 13. Last-owner invariant

The final active OWNER of an organization cannot be:

```text
removed
demoted to ADMIN/EDITOR/VIEWER/BILLING
```

When two or more active owners exist, one owner may be demoted or removed according to actor authority.

## 14. Membership management

OWNER may manage all roles.

ADMIN may manage lower roles but cannot:

```text
modify OWNER/ADMIN peers
promote another member to OWNER/ADMIN
invite OWNER/ADMIN
```

The canonical public Auth router binds `SecureAuthService`, which adds the invite role ceiling rather than relying on frontend options.

## 15. Invitation

Organization invitations are:

```text
organization scoped
email bound
role bound
single-use
expiry bounded
revocable
hash-only at rest
```

Accepting an invite requires an authenticated LUMI User whose normalized email matches the invitation email.

## 16. API tokens

API token plaintext format is opaque and contains a non-secret lookup prefix.

Database stores:

```text
token id
organization_id
creator
name
prefix
SHA-256 secret hash
scopes
expires_at
last_used_at
revoked_at
```

Plaintext is returned exactly once from token creation. Later authentication resolves by prefix, validates full hash and required scope, then updates last-used time.

Revoked/expired/wrong-scope tokens are denied.

## 17. Rate limiting

Security-sensitive entrypoints call a shared rate-limit port.

The reference `InMemorySlidingWindowRateLimiter` exists for deterministic tests/local single-process execution. Production multi-instance runtime must bind shared Redis-backed state; memory-local rate limiting is not accepted as production distributed enforcement.

## 18. Notification delivery

`AuthNotificationPort` is the only supported path for verification/reset/invite plaintext token delivery.

The default production-safe adapter rejects delivery rather than logging or returning secrets.

`SmtpAuthNotificationPort` supports local Mailpit and ordinary SMTP delivery. It sends tokens in action links without logging them. Provider-specific production email adapter/credentials are configuration, not auth-domain state.

## 19. Runnable auth app

`lumi_api.auth_app:app` is a standalone runtime for NODE-16 acceptance and local development.

Development/test defaults:

```text
Mailpit localhost:1025
http://localhost:3000 public URL/origin
non-Secure cookie allowed only for local HTTP development
```

Non-development environments use rejecting notification defaults unless explicitly wired and keep the session cookie Secure.

NODE-17/52 may install the canonical router into the consolidated product app without changing auth semantics.

## 20. Database migrations

```text
0004_auth_security
  users.email_verified_at
  session security fields
  password_credentials
  email_verification_tokens
  password_reset_tokens
  organization_invites
  api_tokens

0005_auth_role_hardening
  normalize legacy organization member roles
  freeze OWNER/ADMIN/EDITOR/VIEWER/BILLING CHECK
```

Migration is expand-first. Older executed migrations are not rewritten.

## 21. Auditing

Registration/login/logout use the existing append-only `audit_events` foundation. Member/token/reset/invite flows are designed to add the same durable audit semantics as persistence integration is completed; no secret material belongs in audit metadata.

NODE-65 later owns retention/legal-hold/governance policy, not authentication semantics.

## 22. Validation layers

### Independent Auth Policy Gate

`.github/workflows/auth-policy.yml` needs only Python 3.12:

```text
compile stdlib policy package
AST dependency-boundary validation
RBAC/tenant/last-owner/token/session/CSRF/API-token/rate-limit unittests
```

It deliberately avoids `uv.lock`.

### Full Auth Integration V2 Gate

`.github/workflows/auth-integration-v2.yml` requires the real Python environment and PostgreSQL:

```text
frozen uv install
static Auth security contract
PostgreSQL infrastructure
Alembic upgrade to current head
alembic check
registration / verification / login / logout / reset integration
invite / API token / last-owner integration
Admin privilege-escalation regression
static persistence schema contract
```

## 23. Explicit security non-goals for V1

Deferred, not faked:

```text
OIDC / enterprise SSO
MFA / passkeys
SCIM
advanced IP/device risk scoring
full Redis distributed rate-limit adapter
production email-provider adapter credentials
```

These are P1/production integrations and must not weaken the local password/session/tenant boundary in the meantime.
