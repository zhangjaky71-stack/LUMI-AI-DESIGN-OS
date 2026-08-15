# NODE-53 — Projects UI Acceptance

Status: **IMPLEMENTED / VALIDATING / not COMPLETE**

Base: `node-52-app-shell-release@29607cfeb9b1a4ae2b50c4280769789855cbb1db`

## Implemented evidence

### Project dashboard

- recent projects;
- grid/list view;
- name search;
- status/workspace/brand filters;
- recent/created/name sorting;
- cursor pagination;
- summary projection fields for preview/status/activity/brand/run/artifact count;
- organization-scoped data access through NODE-52 Shell + query cache.

### New Project

- one natural-language sentence is sufficient;
- optional project name;
- optional reference files;
- optional Brand Kit;
- optional deliverables;
- locale;
- advanced quality profile/budget;
- `直接开始` bypasses optional Step 2;
- Project success is shown only after Gateway confirmation.

### Reference upload

- drag/drop or file picker;
- keyboard-operable picker;
- client type/100MB preflight only as advisory guard;
- user reference role classification;
- project-scoped upload session;
- isolated presigned PUT;
- complete call;
- SCANNING/READY/REJECTED state surface;
- rejected scanner output remains explicitly unavailable.

### Upload security

`LumiApiClient.putPresignedObject()`:

- allows only HTTP/HTTPS URL;
- uses `credentials: omit`;
- does not attach tenant/CSRF/session/Authorization headers;
- preserves upload-contract headers only;
- returns failure on object-store failure.

### Brief and lifecycle

- Structured Brief view;
- significant edit creates BriefVersion;
- project and brief expected-version inputs;
- rename optimistic rollback on VERSION_CONFLICT;
- archive confirmation;
- restore does not restart historical Agent Runs;
- no permanent-delete UI.

## Unit scenarios

```text
cursor paging + org isolation               covered
minimal natural-language create             covered
optional Brand context                      covered
rename VERSION_CONFLICT                     covered
archive / restore                           covered
scanner REJECTED                            covered
BriefVersion append                         covered
presigned upload credentials omitted        covered
non-http presigned URL                       rejected
```

## Browser scenarios

```text
search + cursor load more                    covered
organization switch                         covered
one-sentence Project create                 covered
scanner failure UX                          covered
Brand + deliverable context                 covered
rename conflict rollback                    covered
archive confirmation / restore              covered
Brief v2 -> v3                              covered
```

## Static architecture gate

`scripts/validate_projects_ui.py` verifies:

- Project routes remain Server Component boundaries;
- deterministic E2E backend cannot activate in production;
- production/default resolves to HttpProjectsGateway;
- Project components contain no raw fetch;
- no browser storage business truth;
- upload uses isolated presigned transport;
- object PUT uses credentials omit;
- non-http object URL fails closed;
- minimal create fields exist;
- scanner REJECTED markers remain explicit;
- archive/restore and BriefVersion semantics exist;
- responsive/reduced-motion markers remain present.

NODE-52 App Shell validator is run again as a regression gate.

## Hosted gates

`.github/workflows/projects-ui.yml` requires:

```text
projects-contract
projects-quality
projects-build
projects-security
projects-browser-e2e
```

The production build additionally fails if `.next/static` contains the Projects server-only E2E flag name or server sentinel.

## Local validation limits

Current local environment still does not match repository requirements:

```text
local Node      22.16.0
required Node   24.x
local pnpm      unavailable
local Prettier  unavailable
local tsc       5.8.3
required tsc    6.0.3
```

Therefore no local build/lint/Prettier/Playwright PASS is claimed.

## Upstream dependency truth

```text
NODE-17 Project Core                  SPEC-ONLY / NOT CONNECTED
NODE-18 canonical Project upload      SPEC-ONLY / NOT CONNECTED
NODE-11 generated TS client           SPEC-ONLY / NOT CONNECTED
```

The E2E gateway is not production Project persistence. The HTTP adapter is deliberately provisional until those upstream contracts have executable implementations.

## Completion policy

Do not mark PASS/COMPLETE unless hosted gates execute green and the Project Core/upload/generated-client dependencies are genuinely connected or formally superseded.

Current:

```text
Projects product UI                   IMPLEMENTED
New Project / reference UX            IMPLEMENTED
Structured Brief / BriefVersion UX    IMPLEMENTED
lifecycle / conflict UX               IMPLEMENTED
static architecture gate              hosted execution pending
TS6 typecheck                         hosted execution pending
lint/unit/format                      hosted execution pending
production Next build/security scan   hosted execution pending
Projects Playwright E2E               hosted execution pending
NODE-17/18/11 production adapters     pending upstream implementation
```

Overall: **IMPLEMENTED / VALIDATING / not COMPLETE**.
