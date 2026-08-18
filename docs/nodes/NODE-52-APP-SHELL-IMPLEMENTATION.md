# NODE-52 — App Shell Implementation

> Status: **IMPLEMENTED / VALIDATING / NOT COMPLETE**  
> Branch: `feat/node-52-app-shell`  
> Stack base: `feat/node-51-auto-repair`

## 1. Scope

NODE-52 establishes the shared browser application frame for the Phase 7 frontend. It intentionally does not implement the NODE-53 Projects product, NODE-54 AI Workspace, NODE-55 Infinite Canvas, or later feature surfaces. Those nodes attach to this shell rather than reinventing authentication, tenant context, navigation, API behavior, loading, or error handling.

## 2. Implemented application foundation

`apps/web` is a strict TypeScript Next.js App Router package using React and system fonts only.

Implemented foundation:

- root metadata/layout;
- responsive authenticated App Shell;
- primary navigation;
- organization/workspace/user context presentation;
- protected shell route group;
- unauthenticated sign-in surface;
- Home, Projects handoff, AI Workspace handoff, and Settings routes;
- global loading, not-found, and recoverable error boundaries;
- responsive CSS tokens and component primitives;
- keyboard focus, skip-link, `aria-current`, and reduced-motion affordances.

No mock project, agent, or canvas records are invented by NODE-52.

## 3. API boundary

Browser code uses `apiRequest()` and accepts only same-origin paths beginning with `/api/`.

The Next.js layer rewrites `/api/:path*` to the controlled `LUMI_API_ORIGIN`. This gives browser requests same-origin cookie semantics without exposing a configurable arbitrary fetch proxy.

Server Components and Server Actions use `serverApiRequest()`:

- API origin is validated as a bare `http(s)` origin;
- API paths must be `/api/*` and cannot be absolute URLs;
- incoming httpOnly cookies are forwarded server-to-server;
- request IDs are propagated/generated;
- requests use `cache: no-store`;
- backend redirects are not silently followed by the server client;
- JSON/ProblemDetails responses are normalized through `ApiError`.

No auth bearer token is stored in localStorage, sessionStorage, or manually read through `document.cookie`.

## 4. Session and tenant contract

The shell models an authenticated session as:

```text
user
organization
workspace
permissions[]
expiresAt?
```

`parseAppSession()` validates required IDs/names and fails closed on malformed payloads. `getAppSession()` treats only HTTP 401 as unauthenticated; backend/server/data errors are surfaced instead of being misrepresented as logout. `requireAppSession()` runs in the protected Server Component layout and redirects unauthenticated requests to `/sign-in`.

Frontend navigation does not duplicate backend RBAC. Permissions are available as session context for later UI affordances, while server authorization remains authoritative.

## 5. Navigation and route ownership

Shell routes:

```text
/            Home shell overview
/projects    NODE-53 handoff surface
/workspace   later AI Workspace handoff surface
/settings    authenticated tenant context
/sign-in     unauthenticated entry surface
```

The Projects and Workspace routes are deliberately explicit handoff/empty states. This prevents NODE-52 from fabricating product data or prematurely coupling feature UI to unstable backend contracts.

## 6. Security baseline

Implemented HTTP/browser baseline:

- `X-Content-Type-Options: nosniff`;
- `Referrer-Policy: strict-origin-when-cross-origin`;
- `X-Frame-Options: DENY`;
- restrictive `Permissions-Policy` for camera/microphone/geolocation;
- no browser credential persistence;
- same-origin `/api/*` client boundary;
- controlled backend origin validation.

A production Content Security Policy is intentionally a tracked gap rather than a guessed policy that could break the deployed Next.js/runtime/provider topology.

## 7. Accessibility and responsive behavior

The shell includes:

- skip link to `#main-content`;
- visible `:focus-visible` treatment;
- semantic `nav`, `header`, `main`, headings, lists, and forms;
- `aria-current=page` navigation state;
- loading `aria-busy`;
- recoverable error `role=alert`;
- reduced-motion media query;
- desktop sidebar, compact tablet rail, and mobile horizontal navigation.

These are implementation-level affordances. Browser/automated accessibility E2E remains a validation gap.

## 8. Validation submitted

`tools/node52/validate_app_shell.py` statically enforces:

- required package/config files;
- same-origin API rules;
- cookie-forwarding server client;
- absence of localStorage/sessionStorage/document.cookie auth patterns;
- server-side session guard;
- tenant session contract;
- navigation/accessibility affordances;
- error/loading/not-found boundaries;
- responsive/reduced-motion CSS;
- required shell routes.

`.github/workflows/node-52-app-shell.yml` has two gates:

1. `shell-contract` — static architecture/security/gap-ledger checks;
2. `web-quality` — isolated dependency install, strict TypeScript check, and production Next.js build.

The isolated install does not claim repository-lock validation; that remains in the gap ledger until the real JS workspace lock is regenerated.

## 9. Known production gaps

See `reports/nodes/NODE-52/gap-ledger.json`.

P0 blockers are:

- real auth/session/cookie E2E against the deployed identity service;
- Hosted CI with actual runner steps.

P1 gaps cover repository workspace lock integration, browser/accessibility E2E, and production CSP rollout.

## 10. Completion gate

NODE-52 may be marked COMPLETE only when:

- real login/session/logout/expiry/tenant flows are browser-tested;
- the repository JavaScript workspace and lockfile are regenerated by the actual toolchain and frozen install passes;
- TypeScript and production Next.js build execute successfully on Hosted CI;
- browser route/accessibility tests pass;
- a reviewed production CSP rollout is completed or explicitly accepted by the security gate.

Until then, status remains **IMPLEMENTED / VALIDATING / NOT COMPLETE**.
