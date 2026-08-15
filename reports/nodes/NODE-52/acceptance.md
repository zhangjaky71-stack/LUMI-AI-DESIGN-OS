# NODE-52 — App Shell Acceptance

Status: **IMPLEMENTED / VALIDATING / not COMPLETE**

Base: `node-51-auto-repair-release@0f9e4f835e8ed19650b5b0c942925bde144f1b46`

## Implemented evidence

### Product shell

- stable Next.js App Router root;
- protected `/app` server layout;
- Sidebar / Topbar / main region;
- frozen product route placeholders plus `/invite/accept` auth entry;
- feature-flagged command palette keyboard shell;
- responsive product UI tokens;
- mobile bottom navigation instead of hiding primary navigation;
- existing Canvas engineering routes retained.

### Auth/session boundary

- server-side `ShellSessionAdapter` port;
- production mode always fails closed while NODE-16 is absent, even if the E2E flag is accidentally set;
- deterministic session only under non-production `LUMI_SHELL_E2E_AUTH=1`;
- E2E anonymous cookie forces null session for redirect testing;
- active organization must be present in memberships;
- bounded recent-auth hint;
- API 401 hook clears scoped state and routes to session-expired login;
- invite entry does not write/trust membership client-side;
- generic auth failure language does not reveal account existence;
- real logout/session revocation intentionally remains NODE-16-owned rather than being faked.

### Organization/query boundary

- every cache key includes current org ID;
- old in-flight queries are aborted on switch;
- a loader that ignores abort is rejected after scope movement;
- old cache is cleared;
- project route is reset;
- no session/project business truth in localStorage/sessionStorage.

### API boundary

- one `LumiApiClient` facade for App Shell;
- `/api/v1` base;
- request ID;
- org context header;
- CSRF mutation header;
- idempotency key;
- If-Match;
- typed Problem Details;
- AbortSignal;
- 401 session-expiry hook;
- retries only safe GET and only transient 502/503/504/network cases;
- POST/PATCH are never automatically retried;
- no raw fetch in product shell components/routes.

### Loading/error/accessibility

- skeleton loading;
- reusable empty state;
- SSR-safe offline banner;
- app/project/global error boundaries with retry;
- stack/raw error messages not rendered;
- named semantic navigation/main;
- active route `aria-current`;
- skip link;
- focus-visible rings;
- labeled org switch;
- Ctrl/Cmd+K dialog;
- modal focus loop/Escape close/trigger focus restoration;
- reduced-motion handling.

### Telemetry/flags

- typed public flags resolved on server and serialized read-only;
- server authorization is not represented by mutable client flags;
- command shortcut cannot bypass a disabled command-palette flag;
- safe telemetry event names;
- prompt/image/content/url/token/password/cookie/email-like properties rejected;
- telemetry adapter rejection cannot break the user path.

## Unit scenarios

```text
RFC7807 code surfaced                      covered
safe GET retry only                        covered
POST/PATCH retry prohibition               covered
401 session-expiry hook                    covered
mutation tenant/csrf/idempotency/etag      covered
org A cache != org B cache                 covered
org switch aborts old in-flight work       covered
ignored AbortSignal stale result           rejected
active org without membership              rejected
bounded recent-auth hint                   covered
sensitive telemetry property               rejected
typed presentation flag override           covered
```

## Browser scenarios

```text
anonymous /app -> /login                   covered
authenticated shell render                 covered
organization switch -> /app/projects       covered
skip-navigation keyboard focus             covered
Ctrl+K palette open/focus/Escape/restore    covered
mobile primary navigation                  covered
offline state without shell loss           covered
invite entry remains untrusted              covered
```

## Static architecture gate

`scripts/validate_app_shell.py` verifies route map, Server Component root, production-disabled deterministic auth, API/session-expiry markers, org cache boundary including ignored-abort rejection, telemetry privacy, UI token classes, reduced motion, no new raw fetch, no client env reads, no client server-module imports, no browser-storage truth and no secret-like `NEXT_PUBLIC_*` names.

## Build security gate

The production Next build fails if `.next/static` contains either:

- an injected server-only secret sentinel;
- the server-side `LUMI_SHELL_E2E_AUTH` flag name.

This supplements, rather than replaces, repository-wide secret scanning.

## Upstream dependency truth

```text
NODE-16 production auth/session/RBAC/logout/invite   SPEC-ONLY / NOT CONNECTED
NODE-11 canonical generated TS client               SPEC-ONLY / NOT CONNECTED
```

The E2E session and temporary API facade are explicit ports, not claims that these upstream nodes are complete.

## Hosted gates

`.github/workflows/app-shell.yml` requires:

```text
shell-contract
shell-quality
shell-build
shell-security
shell-browser-e2e
```

### Initial release HEAD evidence

Initial release HEAD: `e68d6c9569d3e31b86130e1446fa56c05c99e5b1`

```text
App Shell run_id:                 31855597482
shell-contract job_id:            94939650769
shell-contract conclusion:        failure
shell-contract runner_id:         0
shell-contract steps:             []
shell-quality:                    skipped
shell-security:                   skipped
shell-build:                      skipped
shell-browser-e2e:                skipped
```

GitHub check annotation:

> The job was not started because recent account payments have failed or your spending limit needs to be increased. Please check the 'Billing & plans' section in your settings

Interpretation: this is the same account-level GitHub Actions billing/spending-limit blocker seen on earlier nodes. The runner never started, so the App Shell architecture validator, pinned TypeScript 6.0.3 typecheck, lint, Vitest suite, Prettier check, production Next build, client-bundle leak scan and Playwright browser smoke were **not executed**. This is not an observed code/test failure and is not PASS.

This evidence commit intentionally creates a new final release HEAD. The final-head hosted run is recorded in PR metadata/body only rather than creating another evidence commit, preventing a commit → workflow → evidence-commit loop.

## Completion policy

Do not mark PASS/COMPLETE unless hosted gates execute green and the NODE-16/NODE-11 production dependencies are genuinely connected or formally superseded by accepted implementations.

Current:

```text
App Shell implementation                  IMPLEMENTED
strict pure-TS boundary audit              passed with available local TS 5.8
static architecture/security gate         not executed on hosted runner
TS6 target typecheck                       not executed on hosted runner
lint/unit/Prettier tests                   not executed on hosted runner
production Next build/client leak scan     not executed on hosted runner
Playwright route/auth/a11y/offline smoke   not executed on hosted runner
hosted blocker                             GitHub billing/spending limit
NODE-16 production session adapter         pending upstream implementation
NODE-11 generated client                   pending upstream implementation
```

Local pure TypeScript validation used the available TypeScript 5.8 compiler with `strict`, `noUncheckedIndexedAccess` and `exactOptionalPropertyTypes` to audit the shell's framework-independent core. It found and led to a fix for the optional unauthorized-handler field. This is useful evidence but is **not** a substitute for the repository's pinned TypeScript 6.0.3 hosted gate.

Overall: **IMPLEMENTED / VALIDATING / not COMPLETE**.
