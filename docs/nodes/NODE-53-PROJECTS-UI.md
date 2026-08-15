# NODE-53 — Projects & New Project UX

> Phase: 7 Frontend Product  
> Status: **IMPLEMENTED / VALIDATING / not COMPLETE**  
> Priority: P0  
> Depends on: NODE-17, NODE-18, NODE-52  
> Produces: Project Dashboard、轻量 New Project、reference upload UX、Structured Brief / BriefVersion、archive/restore

## 1. Implemented outcome

NODE-53 replaces the `/app/projects` placeholder with the first real product workflow on top of NODE-52 App Shell.

Implemented surfaces:

- `/app/projects` Project Dashboard;
- `/app/projects/[projectId]` Project detail / Structured Brief;
- two-step New Project flow;
- staged reference upload UX;
- project search/filter/sort/cursor pagination;
- grid/list view;
- recent projects;
- optimistic rename with VERSION_CONFLICT rollback;
- archive confirmation / restore;
- BriefVersion editing/history;
- responsive/mobile Project UI;
- deterministic E2E backend isolated from production.

Primary implementation:

- `apps/web/src/components/projects/projects-dashboard.tsx`
- `apps/web/src/components/projects/new-project-dialog.tsx`
- `apps/web/src/components/projects/project-detail.tsx`
- `apps/web/src/components/projects/projects.module.css`
- `apps/web/src/lib/projects/types.ts`
- `apps/web/src/lib/projects/projects-gateway.ts`
- `apps/web/src/lib/projects/projects-server.ts`
- `apps/web/e2e/projects.spec.ts`
- `scripts/validate_projects_ui.py`
- `.github/workflows/projects-ui.yml`

## 2. Minimal create rule

A user can start with one natural-language sentence. Technical parameters are not required.

Step 1:

```text
intent                    required
project name              optional
references                optional
```

Step 2 is optional context:

```text
Brand Kit
Deliverables
Locale
Quality Profile
Budget
```

The `直接开始` action skips Step 2.

## 3. Upstream dependency truth

NODE-17 Project Core and the canonical NODE-18 project-scoped upload flow are still specification-only. NODE-53 therefore does not invent a production database or claim a working backend.

Runtime split:

```text
production/default -> HttpProjectsGateway -> /api/v1 contracts
non-production + LUMI_PROJECTS_E2E=1 -> DeterministicProjectsGateway
```

The deterministic gateway is a browser/E2E test backend only. `projects-server.ts` explicitly prevents this mode in `NODE_ENV=production`.

## 4. Project list

Project cards expose the frozen summary projection:

```text
preview
name
status
last activity
brand
active run count
artifact count
```

Supported query dimensions:

```text
name search
status
workspace
brand
sort
cursor pagination
```

Every request is already organization-scoped by NODE-52 `LumiApiClient` + `OrgScopedQueryCache`.

## 5. Project creation and references

Creation never displays success until the gateway confirms the Project.

Reference flow:

```text
local file stage
→ create Project
→ POST /assets/uploads
→ isolated presigned object PUT
→ complete upload
→ SCANNING / READY / REJECTED surfaced explicitly
```

The object PUT is implemented inside `LumiApiClient.putPresignedObject()` so components do not bypass the API/network boundary. It uses `credentials: omit` and never forwards organization/session/CSRF/Authorization headers to object storage.

The current HTTP adapter intentionally treats NODE-17/18 request/response DTOs as provisional until those upstream nodes produce canonical handlers/generated client contracts.

## 6. Reference classification

Supported UI roles:

```text
product
logo
style_reference
content_reference
brand_guide
other
```

Explicit user classification is preserved. Scanner rejection remains visible as `REJECTED`/failure code and is never mapped to READY.

## 7. Structured Brief

Project detail shows:

- objective;
- audience;
- deliverables;
- constraints;
- assumptions;
- locale;
- reference state;
- brief history.

Editing uses optimistic-concurrency inputs:

```text
expected_project_version
expected_brief_version
```

A successful significant edit creates a new `BriefVersion`; history is not mutated in place.

## 8. Rename / archive / restore

Rename is optimistic in the UI but rollback-safe. A `VERSION_CONFLICT` restores the previous name, clears scoped query state and reloads canonical data.

Archive is explicit and confirmed. NODE-53 does not expose permanent delete.

Restore changes Project lifecycle only. It does not restart historical Agent Runs.

## 9. Upload/security boundary

NODE-53 adds one backward-compatible App Shell API capability:

`LumiApiClient.putPresignedObject()`

Safety rules:

- URL must parse;
- only `http:` / `https:`;
- `credentials: omit`;
- only upload-specific headers supplied by the upload contract;
- tenant/session/CSRF/authorization headers are not forwarded;
- upload failure remains failure.

## 10. Tests

Unit/contract coverage includes:

- cursor pagination;
- organization isolation;
- one-sentence create;
- Brand attachment;
- VERSION_CONFLICT;
- archive/restore;
- rejected file scan;
- BriefVersion history;
- presigned upload credential isolation;
- non-http upload URL rejection.

Browser coverage includes:

- search + load more;
- org switch;
- minimal project create;
- failed scanning;
- Brand + deliverable context;
- rename conflict rollback;
- archive/restore;
- BriefVersion editing.

## 11. Definition of Done

```text
Projects UI implementation committed
+ hosted contract/type/lint/unit/build/security/E2E gates green
+ NODE-17 production Project Core connected
+ NODE-18 production upload lifecycle connected
+ NODE-11 canonical generated client replaces provisional HTTP DTO adapter
```

Until those conditions are true, NODE-53 remains **IMPLEMENTED / VALIDATING / not COMPLETE**.

下一节点：NODE-54 AI Workspace。
