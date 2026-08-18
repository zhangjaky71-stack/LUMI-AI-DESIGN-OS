# App Shell Runtime V1

## Purpose

The App Shell is the shared browser boundary for Phase 7. Feature nodes render inside it; they do not create separate authentication, tenant, navigation, API, error, or loading infrastructure.

## Request model

```text
browser
  → Next.js route
     → protected (shell) layout
        → server getAppSession()
           → controlled LUMI_API_ORIGIN + httpOnly cookies
           → backend session contract
        → AppShell(session)
           → feature route
```

Browser API calls remain same-origin:

```text
browser /api/*
  → Next.js rewrite
  → configured LUMI_API_ORIGIN /api/*
```

The browser API helper rejects absolute URLs and paths outside `/api/`.

## Session model

```text
AppSession
├─ user
│  ├─ id
│  ├─ email?
│  └─ displayName?
├─ organization
│  ├─ id
│  └─ name
├─ workspace
│  ├─ id
│  └─ name
├─ permissions[]
└─ expiresAt?
```

Only HTTP 401 maps to unauthenticated. Malformed session payloads and backend failures are not silently converted to logout.

## Security invariants

1. No bearer/session token persistence in localStorage or sessionStorage.
2. Browser client accepts only same-origin `/api/*` paths.
3. Server client accepts only a validated bare `http(s)` API origin.
4. Server client forwards httpOnly cookies, not browser-read tokens.
5. Server API fetches use `cache: no-store` for user/session-sensitive data.
6. Server API redirects are not silently followed.
7. Backend authorization/RBAC remains authoritative.
8. Baseline response headers prevent sniffing, framing, broad referrer leakage, and unneeded device permissions.
9. Production CSP is a separate reviewed rollout, not a guessed header.

## Route ownership

```text
/            NODE-52 shell home
/projects    NODE-53 attachment point
/workspace   AI Workspace attachment point
/settings    shell tenant context
/sign-in     identity-service entry point
```

Shell handoff routes render no fake project/agent/canvas data.

## Accessibility invariants

- skip-to-content link;
- semantic primary navigation;
- `aria-current=page` active route;
- focus-visible ring;
- error alert semantics;
- loading busy state;
- responsive navigation;
- reduced-motion override.

## Error model

Backend non-2xx responses are normalized as `ApiError` with status, code, request ID, trace ID, and ProblemDetails payload when available. Route rendering errors fall into the App Router error boundary with a user retry action and a safe digest reference.

## Configuration

```text
LUMI_API_ORIGIN
LUMI_SESSION_PATH
LUMI_SIGN_IN_PATH
LUMI_SIGN_OUT_PATH
NEXT_TELEMETRY_DISABLED
```

Configured API paths must remain `/api/*`. The default identity paths are placeholders for the existing backend contract and remain subject to real deployed auth E2E validation.

## Handoff contract for feature nodes

Feature UI should:

- render inside `(shell)` routes;
- consume the shared API helpers instead of raw arbitrary fetch wrappers;
- receive/use the authenticated tenant context rather than inventing workspace IDs;
- leave authorization decisions to backend responses;
- use shared shell surfaces for loading/error/navigation behavior;
- avoid mock persisted product state in production routes.

## Validation status

NODE-52 remains **IMPLEMENTED / VALIDATING / NOT COMPLETE** until the real identity flow, repository JS lock, browser E2E/accessibility, production CSP, and Hosted CI gates recorded in `reports/nodes/NODE-52/gap-ledger.json` are closed.
