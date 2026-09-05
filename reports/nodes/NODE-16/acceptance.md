# NODE-16 Acceptance Report — Authentication & Tenant

> Status: **IMPLEMENTED / VALIDATING / BLOCKED_EXTERNAL**  
> Branch: `node-16-auth-tenant`  
> Official node: **NODE-16 — Authentication & Tenant**  
> Base: `node-15-artifact-version-provenance`

## 1. Acceptance intent

NODE-16 establishes the real product identity/tenant security boundary before Project/Asset/Agent runtime endpoints are implemented.

The node must not depend on frontend-hidden controls, prompt behavior or client-supplied tenant/role claims for authorization.

## 2. Standalone security policy layer

`services/auth/src/lumi_auth/` implements dependency-free contracts for:

- OWNER / ADMIN / EDITOR / VIEWER / BILLING;
- deterministic role-permission matrix;
- RequestContext construction from active membership;
- tenant-first object authorization;
- last-owner invariant;
- opaque-token generation/hash/verification;
- single-use token expiry/replay/revocation;
- server-side session expiry/revocation;
- CSRF token + Origin validation;
- Secure/HttpOnly/SameSite cookie contract;
- API token scope/expiry/revocation/hash validation;
- rate-limit port + deterministic in-memory reference limiter.

The policy package is stdlib-only and statically forbidden from importing FastAPI/SQLAlchemy/Argon2/provider/runtime infrastructure.

## 3. Password adapter

`apps/api/src/lumi_api/auth/password.py` is a thin adapter around `argon2-cffi` and selects Argon2id.

It supports:

```text
hash
verify
check_needs_rehash
```

LUMI does not implement custom password cryptography.

The default PasswordHasher and dummy missing-account hash are process-cached so ordinary request construction does not re-run an expensive dummy hash each time.

## 4. Database security migration

### `0004_auth_security`

Adds:

```text
users.email_verified_at
sessions.last_seen_at
sessions.revoked_at
sessions.csrf_token_hash
sessions.user_agent_hash
sessions.ip_risk_metadata
password_credentials
email_verification_tokens
password_reset_tokens
organization_invites
api_tokens
```

Credential/token tables store hashes, not plaintext secret values.

`password_credentials` has an Argon2id-format CHECK.

### `0005_auth_role_hardening`

- normalizes legacy `owner/admin/editor/viewer/billing` organization-member role values to uppercase;
- adds a CHECK for the frozen V1 RBAC role vocabulary.

Current persistence table count remains 46; the migration head advances without introducing a new table.

## 5. Local registration

`AuthService.register_local()` creates in one caller-controlled transaction:

```text
User
Argon2id PasswordCredential
Organization
OWNER membership
Default Workspace
hash-only EmailVerificationToken
AuditEvent
```

The plaintext verification token is returned only to the internal notification boundary.

## 6. Email verification

Verification token:

- opaque high-entropy secret;
- SHA-256 at rest;
- expiry bounded;
- single use;
- replay rejected;
- marks `email_verified_at` on successful consumption.

## 7. Login/session

Login:

- rate-limits by client + normalized email;
- uses generic credential errors for missing/bad/inactive/no-membership cases;
- performs a dummy Argon2 verification path for missing accounts;
- rehashes valid credentials when Argon2 policy changes;
- issues separate session and CSRF opaque secrets;
- stores only their hashes;
- records expiry, last seen, user-agent hash and active organization;
- emits an audit event.

Session plaintext is delivered only through the HttpOnly browser cookie path.

## 8. CSRF/logout

Cookie-authenticated mutations require both an allowed Origin and `X-CSRF-Token` matching the server-side session hash.

Logout:

- rejects missing/expired/revoked session;
- rejects wrong Origin/token;
- sets `revoked_at`;
- maintains the legacy `revoked` bit during migration compatibility;
- expires the browser cookie;
- audits logout.

## 9. Password reset

Reset-request outward behavior is enumeration-safe.

For existing users the internal service creates a hash-only single-use token; for missing users it creates nothing. The public route returns the same accepted response.

Reset confirmation:

- consumes token once;
- Argon2id-hashes the new password;
- increments credential version;
- revokes every active user session;
- rejects token replay.

## 10. Membership and tenant guards

`PrincipalResolver.from_session()` revalidates active membership every time a session resolves an organization. Switching `organization_id` requires membership in the requested organization.

`MembershipService` enforces:

- OWNER may manage all organization roles;
- ADMIN cannot manage OWNER/ADMIN peers;
- ADMIN cannot promote to OWNER/ADMIN;
- last active OWNER cannot be removed/demoted.

Cross-tenant authorization returns a tenant-not-found/forbidden decision before role permissions are considered.

## 11. Invitation

Invitation tokens are organization/email/role bound, hash-only at rest, expiry bounded and single-use.

Accepting an invite requires the authenticated User email to match the invitation email.

Privilege-escalation guard:

```text
OWNER -> may invite all V1 roles
ADMIN -> may invite EDITOR / VIEWER / BILLING only
```

The guard exists in the base AuthService and the canonical `SecureAuthService`, so it does not rely on a hidden UI option.

## 12. API token

API token creation requires `api_token.manage`.

Plaintext is shown only in the create response. Database persists:

```text
prefix
SHA-256 full-token hash
scopes
expiry
last-used
revoked-at
```

Authentication resolves by non-secret prefix then verifies full token hash + required scope. Wrong-scope/expired/revoked tokens fail.

Owner/Admin may revoke organization API tokens.

## 13. HTTP contract

Canonical router factory:

`lumi_api.auth.canonical_router.create_auth_router`

Routes include:

```text
POST   /api/v1/auth/register
POST   /api/v1/auth/verify-email
POST   /api/v1/auth/login
POST   /api/v1/auth/logout
POST   /api/v1/auth/password-reset
POST   /api/v1/auth/password-reset/confirm
POST   /api/v1/auth/organizations/{org}/invites
POST   /api/v1/auth/invites/accept
POST   /api/v1/auth/organizations/{org}/api-tokens
DELETE /api/v1/auth/organizations/{org}/api-tokens/{token}
PATCH  /api/v1/auth/organizations/{org}/members/{user}
DELETE /api/v1/auth/organizations/{org}/members/{user}
```

HTTP failures use Problem Details rather than exposing SQL/Argon2/internal exceptions.

## 14. Secret-delivery boundary

Verification/reset/invite plaintext secrets are delivered only through `AuthNotificationPort`.

Default production-safe implementation rejects unconfigured delivery rather than logging the token or returning it in an HTTP response.

Local SMTP adapter is Mailpit-compatible. Action secret is placed in a URL fragment (`#token=...`), not a query string, so it is not automatically sent in HTTP request URLs/access logs; the frontend must POST it to the corresponding API.

## 15. Runnable local runtime

`lumi_api.auth_app:app` composes:

- DB async session factory;
- canonical secure Auth router;
- Mailpit-compatible SMTP in development/test;
- exact allowed-origin list;
- non-Secure cookie only for local HTTP development/test;
- production-safe rejecting notification default outside local environments.

This allows NODE-16 to be exercised before NODE-17/52 consolidates the full product app.

## 16. Independent policy tests

`services/auth/tests/test_auth_policy.py` covers:

- cross-tenant denial;
- Viewer/Billing permission boundaries;
- last-owner block / two-owner allow case;
- opaque-token hash/replay/expiry/wrong-secret behavior;
- session expiry/revocation;
- CSRF Origin + token checks;
- cookie security contract;
- API-token scope/hash/expiry/revoke semantics;
- sliding-window rate limiting.

`.github/workflows/auth-policy.yml` requires only checkout + Python 3.12 and does not depend on `uv.lock`.

## 17. PostgreSQL + Argon2 integration tests

`test_auth_tenant.py` covers:

- Argon2id hash at rest;
- verification token hash and replay rejection;
- local login and generic invalid-credential path;
- session/CSRF hashes at rest;
- CSRF logout denial/success;
- password reset hash/replay;
- reset revokes all sessions;
- old password denied/new password accepted;
- session principal membership reconstruction;
- invitation single-use;
- API token hash/scope/revoke;
- last-owner DB mutation guard.

`test_auth_privilege_escalation.py` covers ADMIN inability to invite OWNER/ADMIN while still permitting EDITOR.

## 18. Auth security validators

`scripts/validate_auth_policy.py` checks the standalone policy dependency boundary.

`scripts/validate_auth_contracts_v2.py` checks:

- 0004/0005 migration chain;
- required security tables/fields;
- Argon2id DB CHECK;
- hash-only token columns;
- role normalization/CHECK;
- mature Argon2 adapter usage;
- Secure/HttpOnly/SameSite cookie code path;
- CSRF header contract;
- Problem Details;
- verification/reset/invite secret-delivery ports;
- API-token-only one-time plaintext response contract;
- policy implementation dependency boundary.

## 19. CI gates

### Auth Policy

Independent of `uv.lock`:

```text
compile
policy boundary validator
stdlib tests
```

### Auth Integration V2

Requires real locked Python environment + PostgreSQL:

```text
uv sync --frozen
static Auth contract validator
infra up
Alembic head
alembic check
complete Auth PostgreSQL suite
persistence schema contract
```

## 20. Current validation blockers

### GitHub Actions external blocker

Hosted runners cannot start because GitHub account payment/Actions spending requires attention. Previously diagnosed GitHub annotation:

> The job was not started because recent account payments have failed or your spending limit needs to be increased. Please check the 'Billing & plans' section in your settings.

No hosted-runner PASS is claimed while jobs fail before checkout.

### Python lock blocker inherited/extended

The existing `uv.lock` is intentionally stale from NODE-10 dependencies and now additionally lacks the declared `lumi-auth` workspace package + `argon2-cffi` dependency.

The lock file has not been hand-edited. It must be genuinely regenerated by `uv lock` and committed before frozen integration CI can pass.

## 21. Acceptance checklist

- [x] local registration service implemented.
- [x] mature Argon2id adapter implemented.
- [x] email verification token lifecycle implemented.
- [x] login/session/hash/rehash semantics implemented.
- [x] Secure/HttpOnly/SameSite cookie contract implemented.
- [x] CSRF Origin + token contract implemented.
- [x] logout revocation implemented.
- [x] enumeration-safe password-reset request contract implemented.
- [x] reset single-use + revoke-all-sessions implemented.
- [x] five-role RBAC matrix implemented.
- [x] tenant-first authorization implemented.
- [x] last-owner invariant implemented.
- [x] invite single-use/email-bound lifecycle implemented.
- [x] Admin invite privilege-escalation guard implemented.
- [x] API token one-time plaintext/hash/scope/revoke implemented.
- [x] rate-limit policy port/reference limiter implemented.
- [x] secure notification port + local SMTP adapter implemented.
- [x] runnable local Auth app implemented.
- [x] independent Auth Policy Gate committed.
- [x] full Auth Integration V2 Gate committed.
- [ ] real `uv.lock` regenerated and committed.
- [ ] real hosted Auth Policy PASS.
- [ ] real hosted Auth Integration V2 PASS.

## 22. Completion gate

After external recovery:

1. regenerate/commit real `uv.lock`;
2. `uv sync --all-packages --frozen` PASS;
3. Auth Policy workflow PASS;
4. migration empty DB -> current head PASS;
5. `alembic check` PASS;
6. Auth PostgreSQL/Argon2 integration PASS;
7. static persistence schema contract PASS;
8. existing security/contract regression gates remain green;
9. only then mark NODE-16 COMPLETE.

Next official node: **NODE-17 — Project Core**.
