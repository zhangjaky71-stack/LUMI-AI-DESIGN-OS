# LUMI Projects UI Runtime V1

> NODE-53 runtime contract  
> Status: **IMPLEMENTED / VALIDATING / not COMPLETE**

## Purpose

NODE-53 is the Project entry surface for LUMI. It owns frontend project discovery, creation UX, reference staging, Structured Brief presentation/editing, lifecycle actions and browser-state rules. It does not own the Project database, Asset scanner, Object Store, Agent execution or authorization policy.

## Product flow

```text
App Shell
→ Projects Dashboard
→ New Project / Existing Project
→ Structured Brief + References
→ NODE-54 AI Workspace
```

## Dashboard model

The UI consumes a compact `ProjectSummary` projection instead of joining heavy Artifact/Agent tables in the browser:

```text
id
organization_id
workspace_id
name
status
version
created_at
last_activity_at
brand
active_run_count
artifact_count
preview_label
```

The dashboard supports query, status, workspace, brand, sort and cursor. Cursor values are opaque to the component.

## Gateway boundary

`ProjectsGateway` is the only business-data entrypoint used by Projects components.

Operations:

```text
listProjects
getProject
createProject
renameProject
archiveProject
restoreProject
updateBrief
uploadReference
```

Production/default uses `HttpProjectsGateway`. E2E uses `DeterministicProjectsGateway` only when a server bootstrap explicitly chooses E2E mode.

## Production safety

`getProjectsBootstrap()` enables deterministic E2E state only when both conditions are true:

```text
NODE_ENV != production
LUMI_PROJECTS_E2E == 1
```

Production returns `mode=http`, no deterministic seed and no fake Project writes.

## Tenant isolation

NODE-53 reuses NODE-52:

- current organization comes from validated Shell session;
- `LumiApiClient` adds the organization context to API calls;
- `OrgScopedQueryCache` prefixes every cache key with organization ID;
- organization switch aborts old in-flight loads and clears scoped cache;
- a loader result from an old organization is rejected by `QUERY_SCOPE_CHANGED`.

The deterministic gateway also filters every list/detail/mutation by explicit organization ID so E2E can catch cross-tenant UI mistakes.

## New Project

Step 1 requires only natural-language intent. A user can press `直接开始` immediately.

Optional context:

- explicit project name;
- references;
- Brand Kit;
- deliverables;
- locale;
- quality profile;
- budget.

Budget is converted to integer micro-USD, never a JS floating-point monetary value.

## Upload flow

Production adapter sequence:

```text
POST /assets/uploads
→ upload session + presigned URL
→ LumiApiClient.putPresignedObject(File)
→ POST /assets/uploads/{upload_id}/complete
→ scan state surfaced
```

`putPresignedObject()` has a deliberately different security context from API JSON calls:

```text
credentials = omit
no organization header
no CSRF header
no Authorization header
http/https only
```

This prevents an object-storage presigned URL from receiving browser session or tenant credentials.

## Upload state truth

UI states:

```text
LOCAL
UPLOADING
SCANNING
READY
FAILED
```

Asset scan states:

```text
QUEUED
SCANNING
READY
REJECTED
```

A scan result is authoritative. REJECTED is displayed as unavailable with the failure code. SCANNING is not equivalent to failure or ready.

## References

Reference roles are explicit:

```text
product
logo
style_reference
content_reference
brand_guide
other
```

The UI preserves user classification. Future Agent auto-classification may fill only references the user left unclassified.

## Structured Brief and versions

Project detail displays a typed `StructuredBrief` and `brief_version`.

A significant edit sends both:

```text
expected_project_version
expected_brief_version
```

Only a successful gateway response advances the UI to a new BriefVersion. VERSION_CONFLICT reloads canonical state.

## Optimistic rename

Rename is the intentionally small optimistic operation:

1. retain prior list snapshot;
2. change visible name;
3. send PATCH with expected version;
4. on success merge canonical response;
5. on VERSION_CONFLICT restore prior snapshot, clear cache and reload.

Project creation and reference upload are never optimistic-success operations.

## Archive / restore

Archive requires an explicit confirmation dialog. There is no permanent-delete control.

Restore returns the Project to ACTIVE but historical active-run count remains zero in the deterministic contract. The product must not imply old Agent Runs restarted.

## E2E adapter

The deterministic adapter implements actual state transitions in memory rather than static screenshots:

- cursor paging;
- org filter;
- create;
- rename conflict;
- archive/restore;
- upload progress;
- scanner rejection;
- BriefVersion append.

It is testing infrastructure, not production business truth.

## Accessibility and responsive behavior

Projects UI provides:

- real labels for search/filter/form controls;
- keyboard-operable file picker;
- explicit dialog/alertdialog semantics;
- status and alert live regions;
- responsive grid/list layouts;
- mobile bottom-sheet dialog presentation;
- reduced-motion handling.

## Upstream blockers

NODE-53 cannot be marked production-complete until:

1. NODE-17 implements Project Core handlers, persistence and authorization;
2. NODE-18 implements canonical upload session/scanner lifecycle;
3. NODE-11 produces the canonical generated TypeScript client;
4. hosted NODE-53 validation runs execute green.

The current HTTP DTO adapter is intentionally provisional and replaceable behind `ProjectsGateway`.
