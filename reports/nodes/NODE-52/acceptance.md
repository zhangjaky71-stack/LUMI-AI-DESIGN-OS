# NODE-52 — App Shell Acceptance

Status: **IMPLEMENTED / VALIDATING / not COMPLETE**

Base: `node-51-auto-repair-release@0f9e4f835e8ed19650b5b0c942925bde144f1b46`

## Implemented evidence

### Product shell

- stable Next.js App Router root;
- protected `/app` server layout;
- Sidebar / Topbar / main region;
- all frozen route placeholders;
- command palette keyboard shell;
- responsive product UI tokens;
- existing Canvas engineering routes retained.

### Auth/session boundary

- server-side `ShellSessionAdapter` port;
- default/production state fails closed to `/login` while NODE-16 is absent;
- deterministic session only under `LUMI_SHELL_E2E_AUTH=1`;
- E2E anonymous cookie forces null session for redirect testing;
- active organization must be present in memberships;
- generic auth failure language does not reveal account existence.

### Organization/query boundary

- every cache key includes current org ID;
- old in-flight queries are aborted on switch;
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
- retries only safe GET and only transient 502/503/504/network cases;
- no raw fetch in product shell components/routes.

### Loading/error/accessibility

- skeleton loading;
- reusable empty state;
- app/project/global error boundaries;
- stack/raw error messages not rendered;
- semantic navigation/main;
- skip link;
- focus-visible rings;
- labeled org switch;
- Ctrl/Cmd+K dialog;
- modal focus loop/Escape close;
- reduced-motion handling.

### Telemetry/flags

- typed public flags resolved on server and serialized read-only;
- server authorization is not represented by mutable client flags;
- safe telemetry event names;
- prompt/image/content/url/token/password/cookie/email-like properties rejected.

## Unit scenarios

```text
RFC7807 code surfaced                      covered
safe GET retry only                        covered
mutation tenant/csrf/idempotency/etag      covered
org A cache != org B cache                 covered
org switch aborts old in-flight work       covered
active org without membership              rejected
sensitive telemetry property               rejected
typed presentation flag override           covered
```

## Browser scenarios

```text
anonymous /app -> /login                   covered
authenticated shell render                 covered
organization switch -> /app/projects       covered
skip-navigation keyboard focus             covered
Ctrl+K palette open/focus/Escape            covered
```

## Static architecture gate

`scripts/validate_app_shell.py` verifies route map, Server Component root, fail-closed auth adapter, API contract markers, org cache boundary, telemetry privacy, complete UI token classes, reduced motion, no new raw fetch, no client env reads, no client server-module imports, no browser-storage truth and no secret-like `NEXT_PUBLIC_*` names.

## Upstream dependency truth

```text
NODE-16 production auth/session/RBAC        SPEC-ONLY / NOT CONNECTED
NODE-11 canonical generated TS client       SPEC-ONLY / NOT CONNECTED
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

Hosted CI evidence will be recorded after the release branch/PR triggers the workflow.

## Completion policy

Do not mark PASS/COMPLETE unless hosted gates execute green and the NODE-16/NODE-11 production dependencies are genuinely connected or formally superseded by accepted implementations.

Current:

```text
App Shell implementation                  IMPLEMENTED
static architecture/security gate         hosted execution pending
TS6 typecheck                             hosted execution pending
lint/unit tests                           hosted execution pending
production Next build                     hosted execution pending
Playwright route/auth/a11y smoke           hosted execution pending
NODE-16 production session adapter         pending upstream implementation
NODE-11 generated client                  pending upstream implementation
```

Overall: **IMPLEMENTED / VALIDATING / not COMPLETE**.
