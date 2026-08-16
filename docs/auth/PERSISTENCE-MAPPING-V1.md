# NODE-16 Auth Persistence Mapping V1

## Baseline reuse

NODE-16 reuses NODE-10 tables and boundaries where they are already correct:

| Contract | Persistence |
|---|---|
| User identity | `users` |
| Organization | `organizations` |
| Organization membership | `organization_members` |
| Workspace | `workspaces` |
| Workspace membership | `workspace_members` |
| External identity | `auth_identities` |
| Tenant audit | `audit_events` |
| Tenant DB context | `tenant_session()` + `app.current_organization_id` |
| Tenant data isolation | PostgreSQL RLS policies from `20260816_0001` |

The original NODE-10 SQL snapshot remains frozen and is not rewritten.

## Forward migration 20260816_0002

NODE-16 adds:

| Contract | Persistence |
|---|---|
| Email verification status | `users.email_verified_at` |
| Password hash | `password_credentials` |
| Browser session | `auth_sessions` |
| Invite/reset/verification token | `auth_one_time_tokens` |
| Scoped API token | `api_tokens` |
| Pre-tenant security audit | `auth_security_events` |

It also replaces the baseline organization-member role constraint with:

```text
owner / admin / editor / viewer / billing
```

The migration downgrade restores the exact baseline role constraint and removes all NODE-16 structures.

## Secret storage

Database persistence is intentionally hash-only:

```text
password_credentials.password_hash  -> encoded $argon2id$...
auth_sessions.session_hash          -> SHA-256 of random opaque session secret
auth_one_time_tokens.token_hash     -> SHA-256 of random one-time secret
api_tokens.secret_hash              -> SHA-256 of random API bearer token
```

No password, raw session, invite secret, reset secret, verification secret or API bearer secret column exists.

## RLS

`api_tokens` is tenant data and receives an explicit RLS policy using `lumi_current_organization_id()`.

Browser sessions and password credentials are user/authentication data resolved before an organization may be selected; they therefore are not modeled as ordinary tenant rows. Tenant selection happens only after successful authentication and membership resolution.

## Database roles

NODE-10 grants `lumi_app` access only to tables known in 0001. NODE-16 therefore explicitly grants runtime permissions on its new tables:

- CRUD: `password_credentials`, `auth_sessions`, `auth_one_time_tokens`, `api_tokens`;
- SELECT + INSERT only: `auth_security_events`.

UPDATE/DELETE remains revoked for `auth_security_events` to preserve append-only security history.

## Pre-tenant versus tenant audit

`audit_events.organization_id` is non-null and protected by tenant RLS. It is suitable once organization context is known.

A failed login for a nonexistent email has no trustworthy organization. Such events belong to `auth_security_events`, whose `organization_id` is nullable. This prevents inventing tenant identity for authentication telemetry.

## Runtime adapter boundary

The current reference `AuthService` uses `MemoryAuthStore` so auth/session/invite/token rules are executable independently from database availability. SQLAlchemy models and migration 0002 freeze the PostgreSQL shape.

A transactional PostgreSQL AuthStore adapter is still tracked as `AUTH-PERSIST-002`; runtime production persistence must not be claimed complete until that adapter is wired and canonical PostgreSQL tests pass.

## Forward-compatible NODE-10 validation

NODE-16 does not weaken the NODE-10 frozen snapshot. `tools/node10/validate_schema.py` now checks that:

1. all 40 NODE-10 baseline tables still exist in current metadata;
2. the 0001 SQL snapshot still contains exactly those frozen tables and safeguards;
3. global no-Float persistence safety applies to all newer metadata as well.

`tools/node10/run_database_integration.py` discovers the current Alembic head instead of hard-coding `0001`, then runs all existing NODE-10 database invariants. This allows legitimate forward migrations without rewriting the frozen baseline.
