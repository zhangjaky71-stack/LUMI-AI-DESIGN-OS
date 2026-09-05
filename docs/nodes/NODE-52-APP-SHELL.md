# NODE-52 — Frontend App Shell

> Phase: 7 Frontend Product  
> Status: **IMPLEMENTED / VALIDATING / not COMPLETE**  
> Priority: P0  
> Depends on: NODE-02, NODE-11, NODE-16  
> Produces: Next.js App Router product shell, auth/session adapter boundary, navigation, product UI tokens, typed API facade, org-scoped query cache, errors/loading/offline/accessibility/telemetry/flags

## 1. Implemented outcome

The existing `apps/web` application now contains the shared product shell for Phase 7. It does not create a second frontend and does not disturb the NODE-40/41 engineering Canvas routes.

Primary evidence:

- `apps/web/src/app/layout.tsx`
- `apps/web/src/app/app/layout.tsx`
- `apps/web/src/components/app-shell/app-shell-frame.tsx`
- `apps/web/src/components/app-shell/shell-context.tsx`
- `apps/web/src/lib/app-shell/auth-server.ts`
- `apps/web/src/lib/app-shell/api-client.ts`
- `apps/web/src/lib/app-shell/query-cache.ts`
- `apps/web/src/lib/app-shell/telemetry.ts`
- `apps/web/src/app/globals.css`
- `apps/web/e2e/app-shell.spec.ts`
- `scripts/validate_app_shell.py`
- `docs/runtime/APP-SHELL-V1.md`
- `.github/workflows/app-shell.yml`

## 2. Route map

```text
/
/login
/signup
/invite/accept
/app -> /app/projects
/app/projects
/app/projects/[projectId]
/app/brands
/app/assets
/app/team
/app/billing
/app/settings
/admin
```

NODE-53 replaces the Projects placeholder with real Projects UI. NODE-54/55 expand project workspace routes.

## 3. App Router boundary

Root and protected layouts are Server Components. `/app` performs the session check server-side and then passes a serializable bootstrap object into the narrow client provider boundary.

No root-level `use client` wrapper exists.

## 4. Auth dependency truth

NODE-16 is not implemented yet. Production/default shell auth therefore fails closed to `/login`. Deterministic test auth additionally requires both non-production mode and `LUMI_SHELL_E2E_AUTH=1`; setting the flag in a production process still returns no session.

Login/signup UX exists and returns one generic unavailable message; it never reveals whether an account exists. `/invite/accept` is a public entry shell that deliberately does not trust client-supplied invite state. The session contract also exposes a bounded `hasRecentAuthentication()` hint for future sensitive actions.

API 401 responses pass through a typed `on_unauthorized` hook. The App Shell aborts/clears scoped queries and routes to `/login?reason=session-expired`.

A real logout is **not** faked by merely navigating to `/login`; session revocation remains an explicit NODE-16 completion dependency.

## 5. Organization isolation

The session contract requires active organization membership. Query cache keys always include organization ID. Organization changes abort all prior in-flight queries, clear old cache state and reset the project selection route.

A loader that ignores AbortSignal still cannot repopulate old-organization cache or return a trusted cached result: the cache rejects it with `QUERY_SCOPE_CHANGED` after scope movement.

No business/session truth is persisted only in browser storage.

## 6. API boundary

NODE-11 has not generated its canonical TS client yet. `LumiApiClient` is therefore a temporary contract-compatible facade, centralizing `/api/v1`, request ID, tenant context, CSRF, idempotency, If-Match, typed Problem Details, AbortSignal, 401 session-expiry hooks and GET-only retry.

Mutations are never automatically retried, including when they carry an idempotency key. App components contain no scattered raw `fetch('/api/...')` calls.

## 7. UI system

Product UI tokens cover color, spacing, radius, shadow, typography behavior, z-index and motion. They are explicitly separate from customer Brand Tokens.

Shell includes Sidebar, Topbar, organization switcher, role display, feature-flagged command palette, responsive desktop/tablet/mobile states, mobile bottom navigation, loading skeletons, empty-state language and an SSR-safe online/offline banner.

## 8. Error/accessibility/privacy

Implemented:

- root/global error;
- app route error;
- project workspace error;
- request/digest support ID without stack disclosure;
- semantic named nav/main;
- `aria-current` active navigation semantics;
- skip navigation;
- focus-visible ring;
- keyboard command palette;
- modal focus loop, Escape close and trigger-focus restoration;
- reduced motion;
- telemetry sensitive-field rejection;
- telemetry transport failures isolated from the user action path.

## 9. Tests and gates

Unit tests cover API error/retry/401/headers, no mutation retry, org cache isolation/abort/stale-loader rejection, telemetry privacy, feature flags, membership validation and recent-auth semantics.

Playwright covers auth redirect, stable product shell, org switching, keyboard navigation/focus restoration, mobile navigation, offline state and invite entry.

Static validator fails on raw fetch outside the facade, root clientification, production-capable deterministic auth, browser-storage truth, client `process.env`, server-module imports from client code, secret-like `NEXT_PUBLIC_*` names and missing error/privacy/accessibility/session-expiry markers.

The production build job also scans `.next/static` and fails if the server-only E2E auth flag name or an injected server secret sentinel appears in client chunks.

## 10. Known dependency gates

The following are intentionally not falsely claimed:

```text
real production login/session/RBAC/logout  blocked on NODE-16 implementation
canonical generated OpenAPI TS client      blocked on NODE-11 implementation
server-persisted org switch                belongs to NODE-16 session runtime
real invite acceptance                     belongs to NODE-16 session runtime
real Projects business data                NODE-53
```

## 11. Definition of Done

```text
app shell implementation committed
+ hosted type/lint/unit/build/E2E/security gates green
+ NODE-16 production session adapter connected
+ NODE-11 generated client connected
```

Until all three are true, NODE-52 remains **IMPLEMENTED / VALIDATING / not COMPLETE**.

下一节点：NODE-53 Projects UI。
