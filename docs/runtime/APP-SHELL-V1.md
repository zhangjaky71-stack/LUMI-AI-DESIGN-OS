# LUMI App Shell Runtime V1

> NODE-52 implementation contract  
> Status: **IMPLEMENTED / VALIDATING / not COMPLETE**

## 1. Purpose

NODE-52 establishes the stable Next.js App Router shell used by every later product surface. It owns product-level layout, route boundaries, shared UI tokens, the frontend session bridge, organization-scoped query state, API client facade, feature-flag presentation access, safe telemetry, global loading/error/offline states and keyboard-accessible navigation.

It does **not** implement Project business UI, AI Workspace, Infinite Canvas UI, real authentication persistence, RBAC enforcement or the canonical generated OpenAPI client.

## 2. Route contract

```text
/
/login
/signup
/invite/accept
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

Only components that require browser state are marked `use client`: providers, the interactive shell frame, auth form interaction and error reset components. The entire product is intentionally **not** wrapped in a root-level Client Component.

## 4. Authentication boundary

NODE-16 Authentication & Tenant Isolation is still specification-only. NODE-52 therefore does not invent a production auth database or token format.

`DeferredNode16SessionAdapter` behaves as follows:

```text
NODE_ENV=production                       -> null
non-production without E2E flag          -> null
non-production + LUMI_SHELL_E2E_AUTH=1   -> deterministic test session
E2E cookie lumi_e2e_anon=1               -> null
```

The E2E session is an explicit test harness, not a production authentication claim. When NODE-16 is implemented, its server-side session adapter replaces this port without changing page components.

Session validation enforces that the active organization is backed by a session membership. `hasRecentAuthentication()` provides a bounded timestamp check only; it is not authorization. `/invite/accept` is likewise only an entry surface and never writes membership in the browser.

A typed API 401 hook aborts/clears scoped data and routes the user to `/login?reason=session-expired`. Real logout/session revocation remains NODE-16-owned and is intentionally not simulated by a client-only redirect.

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

If a loader ignores AbortSignal and resolves after scope changes, `fetchQuery()` rejects the result with `QUERY_SCOPE_CHANGED` rather than caching or returning it as trusted scoped data.

No Project or session truth is stored in `localStorage`/`sessionStorage`. The current shell does not persist an org switch to a real NODE-16 server session because that runtime does not exist yet.

## 6. API client boundary

NODE-11 API Contract is still specification-only and has not produced the canonical generated TypeScript client. NODE-52 therefore provides one narrow, contract-compatible facade: `LumiApiClient`.

It centralizes:

- `/api/v1` base path;
- `x-request-id`;
- tenant context header;
- CSRF header for mutations;
- `Idempotency-Key`;
- `If-Match`;
- same-origin credentials;
- RFC 7807-style Problem Details;
- AbortSignal propagation;
- 401 session-expiry hook;
- retry only for safe GET requests and only for 502/503/504 or transient network errors.

POST/PATCH mutations are never automatically retried. Components do not call `fetch()` directly. Once NODE-11 generates its canonical client, this facade becomes a thin adapter over that generated package instead of changing page code.

## 7. Feature flags

Public feature flags are typed and read on the server. Only presentation-safe booleans are serialized to client providers. Server-enforced security/authorization decisions are deliberately not represented as client-writable flags.

The command palette shortcut and rendering are both gated by the same public flag. A hidden navigation item is never equivalent to authorization; `/admin` first requires the server session boundary and contains no sensitive console data until a server policy runtime is connected.

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

The shell uses a dark neutral product system with a restrained warm accent. Desktop, compact tablet and mobile-bottom-navigation layouts are covered.

## 9. Loading, empty, offline and error behavior

The shell includes:

- app-level skeleton rather than an infinite spinner;
- empty-state pattern for unconnected product data;
- SSR-safe `useSyncExternalStore` online/offline status;
- app route error boundary with retry;
- project workspace error boundary with retry;
- global error boundary;
- not-found state.

Error UI exposes only a request/digest identifier and never `error.stack` or raw exception messages.

## 10. Accessibility

Implemented baseline:

- named semantic `<nav>` / `<main>` regions;
- `aria-current="page"` active-route semantics;
- skip-navigation link;
- visible `:focus-visible` rings;
- labeled organization selector;
- keyboard `Ctrl/Cmd+K` command palette;
- Escape close;
- two-control modal focus loop;
- focus restoration to the command trigger;
- `aria-modal` dialog semantics;
- reduced-motion media query;
- responsive navigation that remains reachable at mobile widths.

This is a smoke baseline, not a WCAG certification claim.

## 11. Telemetry privacy

`SafeTelemetry` only accepts allowlisted event names and scalar metadata. Property names associated with prompts, images, content, URLs, authorization, cookies, tokens, passwords or email are rejected before the adapter is called.

Adapter promise failures are caught so analytics cannot break user actions. No prompt text, image bytes, generated media or auth secret is sent by NODE-52 telemetry.

## 12. Validation

Unit coverage includes stable Problem Details, GET-only retry, no mutation retry, tenant/CSRF/idempotency/concurrency headers, 401 routing hook, organization cache key isolation, abort plus ignored-abort stale-result rejection, telemetry privacy, active organization membership, recent-auth semantics and typed public feature flags.

Browser coverage includes anonymous auth redirect, authenticated shell render, organization switch, keyboard skip link, command palette focus lifecycle, mobile navigation, offline state and invite entry.

Static gate: `scripts/validate_app_shell.py` checks route presence, Server Component boundaries, production-disabled deterministic auth, API contract markers, session-expiry hook, org-scoped cache, telemetry privacy, UI tokens, raw fetch prohibition, browser-storage prohibition, client env reads and secret-like `NEXT_PUBLIC_*` names.

The hosted production build additionally greps `.next/static` for an injected server secret sentinel and the `LUMI_SHELL_E2E_AUTH` server flag name. Either appearing in client chunks is a failure.

## 13. Completion policy

NODE-52 is not COMPLETE until:

1. hosted `app-shell.yml` gates actually execute green;
2. production auth/session/RBAC/logout/invite flows are connected to NODE-16 or an accepted equivalent;
3. the canonical NODE-11 generated client replaces the temporary facade.

The implementation is usable as the stable frontend shell now, but those upstream dependency gaps remain explicit rather than being hidden behind mocks.
