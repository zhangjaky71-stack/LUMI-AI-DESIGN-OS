# Agent Timeline Runtime V1

## Runtime invariant

The Timeline is a **read projection**, not a second run database.

```text
canonical AIWorkspaceSnapshot
        +
SSE events reduced by applyWorkspaceEvent
        ↓
projectAgentTimeline(snapshot, filter)
        ↓
render-only AgentTimeline
```

No Timeline state is written to `localStorage`, `sessionStorage`, IndexedDB or an independent persistence API.

## Canonical recovery

`refreshCanonical()` fetches `/projects/{projectId}/ai-workspace`. SSE reconnect carries `Last-Event-ID`. After stream completion the workspace is refetched. Timeline reconstruction is therefore deterministic from canonical state.

## Safety boundary

Allowed observability fields are typed safe summaries only. Raw prompt internals, tool payloads, tool results, secrets, stack traces and private reasoning are not part of `AgentTaskSummary` observability contracts.

The frontend additionally redacts suspicious strings through `sanitizeTimelineText()` as defense in depth.

## Progress semantics

A progress meter exists only when both `completed_units` and `total_units` are finite and total is positive. The UI may visually fill the bar from that ratio but must label the progress with the actual count (`2/4`). Unknown work never receives an invented completion percentage.

## Error semantics

Task errors are user-safe objects:

```text
code
safe_message
retrying
request_id
provider_fallback
```

No stack or raw provider payload is rendered. Retry action delegates to the existing versioned Agent Run gateway.

## Approval semantics

Current-run PENDING approval becomes `WAITING_USER` and is pinned above normal timeline items. Stale approval stays visible for audit/user understanding but cannot submit a decision.

## Artifact semantics

Timeline preserves exact `artifact_version_id`. It can invoke existing placement/reference actions and hand the user to Canvas. V1 does not claim an exact Canvas node jump until the AI Workspace placement adapter and Canvas operations gateway have one canonical placement result.

## Production boundary

NODE-57 changes frontend observability contracts and UI projection. It does not claim that every production backend task already emits all optional observability fields. Missing optional fields degrade gracefully to basic task label/status.
