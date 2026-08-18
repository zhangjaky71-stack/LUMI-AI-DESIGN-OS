# AI Workspace Runtime Contract V1

Status: **IMPLEMENTED / VALIDATING / NOT COMPLETE**

## 1. Boundary

NODE-54 owns the product workspace orchestration surface between a durable Project/AgentRun and the user. It does **not** own Infinite Canvas editing (NODE-55) or the later standalone Approval Engine (NODE-62).

The runtime truth chain is:

```text
Project Core AgentRun resource
→ NODE-28 canonical control snapshot
→ durable safe-event replay / SSE projection
→ deterministic browser reducer
→ ArtifactVersion / approval / status UI
```

SSE is never the sole source of truth. After stream EOF, reconnect, approval, or cancellation, the client refetches canonical run/control state.

## 2. Tenant contract

Every business request carries the organization selected by the validated server session as `X-Organization-ID`. The browser receives the organization id as a server-rendered prop; it does not infer or persist tenant identity in localStorage/sessionStorage.

## 3. Run identity

`POST /api/v1/projects/{project_id}/agent-runs` creates the durable run resource. The workspace pins the returned run id in the route:

```text
/workspace?project=<project_id>&run=<agent_run_id>
```

Refreshing the same URL therefore preserves exact run identity. Automatic discovery of a project's most recent run requires a future list/active-run API and is not fabricated by NODE-54.

## 4. Canonical control

NODE-54 adds:

```text
GET /api/v1/agent-runs/{agent_run_id}/control
```

The public projection contains run/project/thread/graph identity, status, resume version, next nodes, sanitized interrupt identities, small context/artifact refs, remaining budget, repair counters, and update time.

Raw LangGraph state, interrupt payload internals, checkpoint metadata beyond the public checkpoint id, and private reasoning are not projected.

## 5. Event stream

NODE-54 adds:

```text
GET /api/v1/agent-runs/{agent_run_id}/events
Accept: text/event-stream
Last-Event-ID: <opaque cursor>
```

Allowed public event types are exactly the NODE-28 safe event set:

```text
run.started
node.started
agent.status
agent.delta
tool.call
task.progress
approval.required
artifact.created
run.completed
run.cancelled
run.waiting_external
```

The API and browser both recursively reject payload keys that could expose private reasoning, prompts/messages, raw model responses, scratchpads, or raw tool output.

The browser implements SSE through `fetch + ReadableStream`, not EventSource, so tenant headers, explicit `Last-Event-ID`, AbortSignal, and bounded reconnect backoff remain under product control.

## 6. Artifact identity

An Artifact card is admitted only when an event contains both:

```text
artifact_id
artifact_version_id
```

`version_number` is optional presentation metadata. Missing exact version identity produces a warning timeline item and no clickable/selectable Artifact card.

NODE-54 stage selection therefore never aliases an Artifact head that may have changed concurrently.

## 7. Canvas selection handoff

NODE-55 supplies:

```json
{
  "selected_node_ids": ["..."],
  "design_document_version": 17
}
```

NODE-54 serializes this exact selection into AgentRun `client_context`. Duplicate/empty node ids are removed and a non-positive document version is rejected. Until NODE-55 is implemented, the workspace truthfully renders “no canvas selection.”

## 8. Approval

NODE-28 currently proves approval resume with:

```json
{"action": "approve"}
```

Before submitting approval, the browser refetches canonical control and verifies the same `resume_version` and interrupt id are still current/resumable. The backend remains the final stale fence.

NODE-54 intentionally does not invent a public reject value. Reject semantics and richer approval payloads remain a later Approval Engine contract.

## 9. Cancellation

Stop uses the existing public AgentRun cancellation resource. UI copy explicitly states that provider work already accepted externally may still require reconciliation; cancellation never claims to undo irreversible side effects.

## 10. Message history

The current Project Core AgentRun model does not expose a durable conversation transcript. NODE-54 renders safe run events and the user's just-submitted command during the current browser session, but does not fabricate persisted chat history. Durable conversation history is a separate production gap.

## 11. Failure modes

- Missing workspace control/event composition: API returns 503; UI continues refreshing the durable Project Core run and displays a degraded-live-status notice.
- Stream EOF/error: refetch canonical state, back off, reconnect with `Last-Event-ID`.
- Duplicate event: deterministic reducer ignores the duplicate event id.
- Stale approval: do not submit; replace local control with the fresh canonical snapshot.
- Artifact event without exact version: warning only; no Artifact card.
- Unknown/private event payload: fail closed rather than render it.
