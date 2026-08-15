# AI Workspace Runtime V1

> NODE-54 runtime contract  
> Status: implementation staged; hosted validation and production dependencies pending.

## Route and ownership

The workspace lives at `/app/projects/{projectId}/workspace`. Browser state is limited to presentation, current selection, reconnect state and transient input. Project, AgentRun, Approval, Artifact and Canvas document state remain canonical on the server.

Production/default mode is HTTP/SSE. A deterministic adapter is enabled only when `NODE_ENV !== production` and `LUMI_AI_WORKSPACE_E2E=1`.

## Command contract

```text
GET  /projects/{projectId}/ai-workspace
POST /projects/{projectId}/agent-runs
POST /agent-runs/{runId}/pause
POST /agent-runs/{runId}/resume
POST /agent-runs/{runId}/cancel
POST /agent-runs/{runId}/tasks/{taskId}/retry
POST /approvals/{approvalId}/decisions
POST /canvas/documents/{documentId}/artifact-placements
```

Starting a run binds `project_id`, prompt, `selected_node_ids`, `document_version`, READY `reference_asset_ids` and exact `reference_artifact_version_ids`.

Run controls bind `expected_run_version`. Artifact placement binds `artifact_id`, exact `artifact_version_id`, `document_id` and `expected_document_version`.

## Realtime

SSE uses same-origin credentials, explicit organization scope and `Last-Event-ID`. The reducer keeps a bounded seen-event set and ignores duplicate event IDs. After a clean stream finish the client refetches canonical workspace state.

Projected browser events are safe product events such as `message.created`, `artifact.created`, `approval.required` and `run.status`; the frontend data model contains only user-visible progress and product state.

## Approval

An approval is actionable only when it is `PENDING`, belongs to the current run, matches the current run version and is not expired. Supported decisions are APPROVE, REJECT and REQUEST_CHANGES. Request Changes requires a note. Stale cards remain visible but disabled.

## Canvas boundary

NODE-54 implements versioned Canvas preview, node selection, locked-identity context and exact Artifact placement. It intentionally does not claim full Infinite Canvas editing; NODE-55 owns professional pan/zoom, scene graph interactions, transforms and richer editor behavior.

## Mobile

Desktop presents Agent / Canvas / Context together. Mobile uses focused Agent, Canvas and Context tabs so prompt, preview and approval remain usable without compressing the desktop layout.

## Deterministic E2E fixture

The non-production fixture provides Canvas document v7, Hero Product / Headline / Offer Badge nodes, READY product and brand-guide references, a provider fallback warning, an intentionally stale approval, one intentionally duplicated realtime event, Artifact v1 and an approval interrupt.

This proves at-least-once dedupe, reconnect, exact-version placement and stale-decision protection.

## Validation

Static gate:

```text
python scripts/validate_ai_workspace.py
```

Hosted gates:

```text
ai-workspace-contract
ai-workspace-quality
ai-workspace-build
ai-workspace-security
ai-workspace-browser-e2e
```

The workflow also reruns App Shell and Projects regressions. NODE-54 remains `IMPLEMENTED / VALIDATING / NOT COMPLETE` until hosted gates execute green and the required production Agent/realtime/Canvas/API dependencies are connected or formally superseded.
