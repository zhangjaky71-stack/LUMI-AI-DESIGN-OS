# NODE-54 — AI Design Workspace

> Phase: 7 Frontend Product  
> Status: IMPLEMENTED / VALIDATING / NOT COMPLETE  
> Priority: P0 / CORE UX  
> Depends on: NODE-28, NODE-33, NODE-42, NODE-52, NODE-53  
> Produces: project-scoped Chat + Canvas workspace, safe Streaming, versioned run controls, selected-object context, Artifact and Approval workflow

---

## 1. Goal

Build LUMI’s core design workspace so a user can drive an Agent with natural language while simultaneously seeing Canvas state, progress, exact Artifact versions, context and approvals.

The implementation preserves NODE-53 Project/Structured Brief UX and adds:

```text
/app/projects/{projectId}/workspace
```

NODE-55 will replace the current versioned Canvas preview/selection surface with the Infinite Canvas editor without changing the command/version contracts established here.

## 2. Product layout

Desktop is a three-surface workspace:

```text
Agent / Chat     Canvas / Selection     Inspector / Context
```

- Canvas keeps the flexible center column.
- Context is explicit rather than implicit.
- Mobile switches to focused Agent/Canvas/Context tabs instead of squeezing three columns.

## 3. Prompt composer

P0 implemented:

- multiline prompt;
- `Ctrl/Cmd + Enter` send;
- selected Canvas node context chips;
- READY project references;
- exact Artifact version references;
- explicit target labels including `locked identity`.

Start payload binds the user request to:

```text
project_id
selected_node_ids
document_version
reference_asset_ids
reference_artifact_version_ids
```

Slash commands remain P1.

## 4. Safe message model

Implemented UI kinds:

```text
USER
STATUS
ANSWER
ARTIFACT
APPROVAL
WARNING
ERROR
```

Private chain-of-thought is not a type field and is never displayed. Only safe status/progress summaries are allowed.

## 5. Realtime / SSE

Implemented behavior:

- same-origin SSE fetch;
- explicit organization scope header;
- `Last-Event-ID` reconnect;
- event-id dedupe for at-least-once delivery;
- visible offline/reconnecting state;
- old stream abort on navigation/control/new run;
- canonical API refetch after stream completion.

SSE is an acceleration/projection channel, not the canonical database.

## 6. Run controls

Implemented:

```text
Start
Pause
Resume
Stop / Cancel
Retry failed retryable task
```

Every mutation is version-bound with `expected_run_version`. Stale commands reload canonical state instead of overwriting newer state.

## 7. Artifact cards

Implemented:

- preview label;
- explicit version;
- exact `artifact_version_id`;
- place on Canvas;
- use exact version as next-run reference;
- compare placeholder reserved for NODE-59.

Canvas placement also requires `expected_document_version`, so “latest artifact/latest document” ambiguity cannot silently mutate the wrong version.

## 8. Selection context

The current Canvas selection surface exposes selectable nodes and sends selected node IDs plus the active document version to Agent commands.

The UX shows:

```text
2 selected
Hero Product · locked identity
Headline
Document vN
```

This contract is intentionally ready for NODE-55 Infinite Canvas.

## 9. Approval cards

Implemented:

- approval title and description;
- impact;
- estimated incremental cost when present;
- Approve;
- Reject;
- Request Changes + required note;
- stale/expired protection.

A decision is disabled unless the approval still matches the current run and expected run version.

## 10. Warnings and context transparency

Implemented warning surface includes provider-degraded/fallback scenarios. The model can later carry budget, hard constraint, rights and validation warnings through the same safe message kind.

Inspector shows Brand, references, selected nodes and document version. It never exposes system prompts/private reasoning.

## 11. Production adapter boundary

Production/default uses a typed HTTP/SSE adapter. Deterministic behavior is available only in non-production E2E mode:

```text
NODE_ENV !== production
LUMI_AI_WORKSPACE_E2E = 1
```

Production client chunks are scanned to ensure that server-only E2E control name is not leaked.

The adapter is intentionally narrow because NODE-28/NODE-33/NODE-42 and canonical generated API contracts still need full production integration. NODE-54 does not pretend a browser mock is a backend implementation.

## 12. Test matrix

Unit:

- SSE decode;
- duplicate event;
- stale approval;
- selected-node edit context;
- pause/resume/stop version conflict;
- Last-Event-ID resume;
- exact Artifact/document version placement.

Playwright:

- project Chat + Canvas coexist;
- selection context visible;
- streaming + duplicate suppression;
- Artifact → Approval;
- stale approval disabled;
- pause/resume/stop;
- exact Artifact placement;
- provider warning;
- private-reasoning non-exposure;
- mobile focused panels.

## 13. CI

Workflow: `.github/workflows/ai-workspace.yml`

Gates:

```text
ai-workspace-contract
ai-workspace-quality
ai-workspace-build
ai-workspace-security
ai-workspace-browser-e2e
```

It also reruns NODE-52 App Shell and NODE-53 Projects regression validation.

## 14. Acceptance checklist

- [x] Chat and Canvas are in one Project workspace.
- [x] Streaming client supports reconnect with `Last-Event-ID`.
- [x] duplicate realtime events are idempotently ignored.
- [x] selected objects + document version enter Agent commands.
- [x] Start/Pause/Resume/Stop/Retry contracts exist.
- [x] Approval is embedded and stale decisions are blocked.
- [x] Artifact actions bind exact versions.
- [x] provider warnings are visible.
- [x] mobile does not squeeze the desktop three-column layout.
- [x] private chain-of-thought is not exposed by the UI model.
- [ ] pinned hosted TypeScript/lint/unit/build/Playwright gates execute green.
- [ ] NODE-28/NODE-33/NODE-42/canonical client production dependencies are actually connected or formally superseded.

## 15. Definition of Done

Current state:

```text
implementation                 DONE
static architecture validator DONE locally after commit candidate assembly
hosted frontend gates         PENDING EXECUTION
production runtime adapters   UPSTREAM DEPENDENCY
```

NODE-54 remains **IMPLEMENTED / VALIDATING / NOT COMPLETE** until required hosted gates execute green and production dependencies are real.

Next node: **NODE-55 — Infinite Canvas UI**.
