# Agent Timeline Runtime Contract V1

Status: NODE-57 core implemented, validating, not complete.

## 1. Truth model

Timeline has two source layers:

```text
RunControlSnapshot (canonical current state)
  -> Current Stage projection

Durable AgentEventReplayPort / SSE
  -> historical public timeline items
```

A page refresh MUST first recover a meaningful current stage from canonical control state. Historical activity is recovered by durable event replay from `Last-Event-ID=null` on a fresh browser session. Browser-only event buffers are never authoritative.

If durable replay is unavailable, the UI degrades to canonical current-stage observability and explicitly does not claim full history recovery.

## 2. Public item model

```text
id
type: run | task | tool | progress | approval | artifact | error | status
status: running | waiting | completed | failed | cancelled | info
label
safeSummary?
occurredAt?
taskId?
node?
artifact? exact ArtifactVersion only
errorCode?
progress? { current, total }
costSummary?
retrySummary?
```

No item contains arbitrary raw payload.

## 3. Safe projection

The backend public event schema recursively rejects private reasoning and secret-like keys. The browser parser repeats the same defense before reducer ingestion. The Timeline projector then reads only an explicit field allowlist such as `safe_summary`, `message`, `status`, `task_id`, `node`, `tool_name`, `current`, `total`, retry/fallback fields, cost/credit fields, error code, and exact Artifact identity.

The UI never renders raw tool payloads, request headers, credentials, tokens, prompts, messages, chain-of-thought, scratchpad, raw model responses or stack traces.

## 4. Current stage

`canonicalTimelineItem()` derives the current stage from:

- `status`;
- `task_id`;
- `next_nodes`;
- interrupts;
- `error_code`;
- route;
- repair iteration;
- artifact reference count;
- canonical `updated_at`.

Approval/review interrupts take precedence and render as waiting. Errors render from stable error code only. No internal state or reasoning is inferred.

## 5. Historical events

Safe event types are projected semantically:

- `run.started/completed/cancelled` -> run items;
- `node.started` -> task item;
- `agent.status/delta` -> safe status item;
- `tool.call` -> meaningful public action label;
- `task.progress` -> task progress;
- `approval.required` -> waiting approval item;
- `artifact.created` -> exact artifact item or failed/incomplete item;
- `run.waiting_external` -> waiting external item.

Event IDs are deduplicated by both SSE consumer and reducer. `Last-Event-ID` drives replay on reconnect.

## 6. Progress

NODE-57 MUST NOT invent a percentage from opaque reasoning or generic scalar progress. A visual progress bar is shown only when both public integer `current` and `total` are present, `total > 0`, and `0 <= current <= total`.

## 7. Retry / fallback

Retry and provider fallback are displayed only when explicit public fields are emitted (`retrying`, `retry_attempt`, `fallback_provider`, `provider_fallback`, `provider`). No provider switch is inferred from timing or failures.

## 8. Cost

Cost/credits are optional and are summarized only from explicit public numeric fields (`actual_cost_usd`, `estimated_cost_usd`, `cost_usd`, `credits_used`, `credits`). Timeline does not reconstruct cost from token counts.

## 9. Artifact navigation

A Timeline artifact action exists only when both `artifact_id` and `artifact_version_id` are present. Opening it passes the exact version reference into the existing NODE-54/NODE-55 Canvas selection flow. A partial artifact event never becomes a clickable latest-version link.

## 10. Approval

The canonical current-stage approval action remains visible independently of historical event replay. The actual resume mutation continues to use NODE-54's stale-fenced `resume_version + interrupt_id` validation before resuming.

## 11. Failure semantics

- Replay duplicate: ignore by event id.
- Replay disconnect: reconnect with Last-Event-ID; canonical state is refetched on stream end.
- Replay unavailable: current canonical state remains visible; history is incomplete.
- Error event: display safe summary/error code only.
- Secret/private payload key: reject at API/browser parser boundary.
- Artifact missing exact version: display incomplete event, no Canvas link.
- Unknown progress scalar: no percentage/bar.

## 12. Remaining P0

See `reports/nodes/NODE-57/gap-ledger.json`. Full completion requires production durable event replay composition, standardized producer payload semantics for retry/fallback/cost/user-action errors, browser refresh/reconnect/approval/artifact E2E, and hosted green evidence.