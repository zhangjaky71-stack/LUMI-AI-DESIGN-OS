# LUMI App Shell Runtime V1

> NODE-52 implementation contract  
> Status: **IMPLEMENTED / VALIDATING / not COMPLETE**

## 1. Purpose

NODE-52 establishes the stable Next.js App Router shell used by every later product surface. It owns product-level layout, route boundaries, shared UI tokens, the frontend session bridge, organization-scoped query state, API client facade, feature-flag presentation access, safe telemetry, global loading/error states and keyboard-accessible navigation.

It does **not** implement Project business UI, AI Workspace, Infinite Canvas UI, real authentication persistence, RBAC enforcement or the canonical generated OpenAPI client.

## 2. Route contract

```text
/
/login
/signup
/app
/app/projects
/app/projects/[projectId]
/app/brands
/app/assets
/app/team
/app/billing
/app/settings
/admin
```

Existing engineering routes such as `/canvas-engine` remain untouched so NODE-40/41 browser harnesses continue to exist.

## 3. Server/client boundary

`src/app/layout.tsx` is a Server Component. The protected `/app` layout is also a Server Component and calls `requireShellSession()` before rendering the client interaction boundary.

Only components that require browser state are marked `use client`:

- `ShellProviders`;
- `AppShellFrame`;
- auth form interaction;
- route/global error reset components.

The entire product is intentionally **not** wrapped in a root-level Client Component.

## 4. Authentication boundary

NODE-16 Authentication & Tenant Isolation is still specification-only. NODE-52 therefore does not invent a production auth database or token format.

`DeferredNode16SessionAdapter` behaves as follows:

```text
production/default -> null -> /login
LUMI_SHELL_E2E_AUTH=1 -> deterministic test session
E2E cookie lumi_e2e_anon=1 -> null -> auth redirect test
```

The E2E session is an explicit test harness, not a production authentication claim. When NODE-16 is implemented, its server-side session adapter replaces this port without changing page components.

Session validation already enforces that the active organization is backed by a session membership. Cross-organization active IDs fail closed.

## 5. Organization switching and cache isolation

`OrgScopedQueryCache` prepends the current organization ID to every key:

```text
[organization_id, ...query_key]
```

Switching organization:

1. aborts every old in-flight query;
2. clears the scoped cache;
3. changes the local active organization;
4. resets navigation to `/app/projects`;
5. emits only safe aggregate telemetry.

No Project or session truth is stored in `localStorage`/`sessionStorage`.

The current shell does not persist an org switch to a real NODE-16 server session because that runtime does not exist yet. That write belongs to the future auth adapter.

## 6. API client boundary

NODE-11 API Contract is still specification-only and has not produced the canonical generated TypeScript client. NODE-52 therefore provides one narrow, contract-compatible facade: `LumiApiClient`.

It centralizes:

- `/api/v1` base path;
- `x-request-id`;
- tenant header;
- CSRF header for mutations;
- `Idempotency-Key`;
- `If-Match`;
- same-origin credentials;
- RFC 7807-style Problem Details;
- retry only for safe GET requests and only for 502/503/504 or transient network errors;
- AbortSignal propagation.

Components do not call `fetch()` directly. Once NODE-11 generates its canonical client, this facade becomes a thin adapter over that generated package instead of changing page code.

## 7. Feature flags

Public feature flags are typed and read on the server. Only presentation-safe booleans are serialized to client providers. Server-enforced security/authorization decisions are deliberately not represented as client-writable flags.

A hidden client navigation item is never equivalent to authorization; `/admin` explicitly contains no sensitive console data until a server policy runtime is connected.

## 8. UI design tokens

Product UI tokens live in `globals.css` and are distinct from user Brand Tokens:

```text
color/background/border
spacing
radius
shadow
typography
z-index
motion
```

The shell uses a dark neutral product system with a restrained warm accent. These tokens style LUMI itself and must never be interpreted as a customer's brand kit.

## 9. Loading, empty and error behavior

The shell includes:

- app-level skeleton rather than an infinite spinner;
- empty-state pattern for unconnected product data;
- app route error boundary;
- project workspace error boundary;
- global error boundary;
- not-found state.

Error UI exposes only a request/digest identifier and never `error.stack` or raw exception messages.

## 10. Accessibility

Implemented baseline:

- semantic `<nav>` / `<main>` regions;
- skip-navigation link;
- visible `:focus-visible` rings;
- labeled organization selector;
- keyboard `Ctrl/Cmd+K` command palette;
- Escape close;
- two-control modal focus loop;
- `aria-modal` dialog semantics;
- reduced-motion media query;
- responsive navigation.

This is a smoke baseline, not a WCAG certification claim.

## 11. Telemetry privacy

`SafeTelemetry` only accepts allowlisted event names and scalar metadata. Property names associated with prompts, images, content, URLs, authorization, cookies, tokens, passwords or email are rejected before the adapter is called.

No prompt text, image bytes, generated media or auth secret is sent by NODE-52 telemetry.

## 12. Validation

Unit coverage:

- stable Problem Details errors;
- GET-only retry;
- tenant/CSRF/idempotency/concurrency headers;
- organization cache key isolation;
- in-flight cancellation on organization change;
- sensitive telemetry rejection;
- active organization membership contract;
- typed public feature flags.

Browser coverage:

- anonymous auth redirect;
- authenticated shell render;
- organization switch;
- keyboard skip link;
- command palette open/focus/close.

Static gate: `scripts/validate_app_shell.py` checks route presence, Server Component boundaries, auth fail-closed behavior, API contract markers, org-scoped cache, telemetry privacy, UI tokens, raw fetch prohibition, browser-storage prohibition, client env reads and secret-like `NEXT_PUBLIC_*` names.

## 13. Completion policy

NODE-52 is not COMPLETE until:

1. hosted `app-shell.yml` gates actually execute green;
2. production auth is connected to NODE-16 or its equivalent accepted implementation;
3. the canonical NODE-11 generated client replaces the temporary facade.

The implementation is usable as the stable frontend shell now, but those upstream dependency gaps remain explicit rather than being hidden behind mocks.
