# NODE-53 — Projects UI Implementation

> Status: **IMPLEMENTED / VALIDATING / NOT COMPLETE**  
> Branch: `feat/node-53-projects-ui`  
> Stack base: `feat/node-52-app-shell`

## 1. Scope

NODE-53 turns the App Shell `/projects` handoff into a real Project Core product surface. It owns project discovery, new-project/brief capture, project detail, and the stable handoff into the AI Workspace. It does not implement NODE-54 agent/chat/canvas execution.

## 2. Real data path

The UI does not render mock project records.

```text
Projects Dashboard
  → server listProjects()
  → shared NODE-52 serverApiRequest()
  → /api/v1/projects
  → parseProjectCollection()
  → ProjectSummary[]
```

Project detail uses the same adapter and exact project ID path. API payload parsing accepts the frontend-facing collection shapes `items`, `projects`, `results`, or a direct array after the shared API envelope is unwrapped. Snake/camel timestamp fields and audience fields are normalized at the adapter boundary rather than in page components.

## 3. Projects Dashboard

Implemented dashboard behavior:

- real server-rendered project collection;
- search over project name/description;
- status filtering;
- last-updated sorting;
- result count and filtered count;
- real zero-project empty state;
- no-results filter state;
- responsive project cards;
- direct New Project action.

At the current scale boundary filtering happens after server retrieval. Cursor pagination and backend-side q/status filtering remain a tracked P1 gap rather than an invented contract.

## 4. New Project + Brief

The New Project route captures:

- project name;
- description;
- objective;
- audience;
- deliverables;
- explicit constraints.

The form uses React 19 `useActionState` and `useFormStatus`, but validation and side effects execute in a server action.

Safety/quality behavior:

- stable per-form operation UUID;
- `Idempotency-Key` sent to Project Core;
- server-side length/count validation;
- field-level accessible error messages;
- no localStorage/sessionStorage draft identity;
- no client-supplied organization/workspace ID;
- successful creation redirects to the returned durable project ID.

The create+brief payload mapping is deliberately isolated in `src/lib/projects/api.ts`; deployed OpenAPI conformance is a P0 completion gate.

## 5. Project Detail

The project detail surface renders only persisted project data:

- status;
- name/description;
- creative objective;
- audience;
- deliverables;
- hard constraints.

The page exposes a stable `workspace?project=<id>` handoff. It does not invent artifact, agent, task, canvas, or review records before NODE-54+ implement those surfaces.

## 6. Route transition from NODE-52

NODE-52 intentionally left `/projects` as a handoff placeholder. NODE-53 adds the Next.js 16 `proxy.ts` boundary so `/projects` redirects to `/projects/dashboard` without mutating the previous node's implementation history. The dashboard, new-project and detail routes then live under the existing protected App Shell layout and inherit its session/tenant/API/error/navigation contracts.

## 7. Accessibility and UX

Implemented affordances include:

- semantic search form;
- visually hidden filter labels;
- field labels and required state;
- `aria-invalid` + error descriptions;
- `role=alert` action errors;
- pending submit state;
- semantic breadcrumb;
- real empty states;
- responsive grid/form/detail layouts;
- focus behavior inherited from the App Shell.

## 8. Validation submitted

`tools/node53/validate_projects_ui.py` enforces:

- shared server API usage;
- `/api/v1/projects` resource isolation;
- idempotency key;
- project/brief parser boundary;
- real `listProjects()` use in Dashboard;
- no known mock-project patterns;
- server action validation;
- accessible form state;
- detail/workspace handoff;
- `/projects` proxy redirect;
- absence of localStorage/sessionStorage/document.cookie auth state.

`.github/workflows/node-53-projects-ui.yml` runs the static contract gate, TypeScript check and full production web build.

## 9. Known gaps

See `reports/nodes/NODE-53/gap-ledger.json`.

P0 completion blockers:

- deployed Project Core/OpenAPI create/list/detail/brief conformance;
- Hosted CI with actual executed steps.

P1 gaps cover cursor/backend filtering, post-create brief/status/archive lifecycle, and browser E2E.

## 10. Completion gate

NODE-53 may be marked COMPLETE only after:

- Project Core contract tests prove the deployed endpoint and create+brief schema;
- real authenticated browser flow proves list → create → detail → workspace handoff;
- idempotent retry and validation/conflict errors are exercised;
- production-scale pagination/filtering is implemented or explicitly scoped out by product acceptance;
- Hosted CI executes and passes the NODE-53 gates.

Until then, status remains **IMPLEMENTED / VALIDATING / NOT COMPLETE**.
