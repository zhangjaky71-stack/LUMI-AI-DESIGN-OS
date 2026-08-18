# NODE-54 — AI Workspace Implementation

Status: **IMPLEMENTED / VALIDATING / NOT COMPLETE**  
Branch: `feat/node-54-ai-workspace`  
Stack base: `feat/node-53-projects-ui`

## Implemented product path

```text
Project Detail
→ /workspace?project=<project_id>[&run=<agent_run_id>]
→ validated server session + exact Project context
→ create durable Project Core AgentRun
→ persist run id in URL
→ canonical NODE-28 control snapshot
→ resumable safe-event SSE
→ deterministic browser reducer
→ status / approval / exact ArtifactVersion UI
```

## API additions

- `GET /api/v1/agent-runs/{id}/control`
  - tenant-scoped canonical run projection;
  - no raw LangGraph state;
  - no interrupt private payload;
  - exact graph/code/resume identity remains visible for support/recovery.
- `GET /api/v1/agent-runs/{id}/events`
  - `text/event-stream`;
  - `Last-Event-ID` replay cursor;
  - no proxy buffering;
  - safe NODE-28 event allowlist only.
- `ControlStoreAgentWorkspaceService`
  - reads the existing NODE-28 control store;
  - requires a durable event replay port;
  - rejects cross-run/project replay records.

The API and browser both recursively reject private reasoning/raw model fields.

## Browser runtime

- tenant id comes from the validated server session, never local storage;
- durable AgentRun creation uses an idempotency key;
- active run identity is addressable via URL;
- `fetch + ReadableStream` SSE supports tenant headers, abort, explicit cursor and bounded reconnect;
- clean EOF/error both trigger canonical state refetch before reconnect;
- duplicate event ids are ignored;
- a 10-second canonical refresh protects against missed/reordered projection signals;
- control/event service 503 produces an explicit degraded-live-status notice rather than mock events.

## Run controls

- Start: creates a durable Project Core AgentRun.
- Stop: uses the existing public cancel resource and warns that already accepted external provider work may still need reconciliation.
- Approve: NODE-28-proven `{"action":"approve"}` value only.
- Approval stale fence: refetch canonical control and require unchanged `resume_version` + interrupt id before resume.
- Reject/Request changes: deliberately not invented because current public control contract does not standardize those values yet.

## Artifact / Canvas boundary

Artifact UI admits a card only when `artifact.created` contains both `artifact_id` and exact `artifact_version_id`. Missing exact version becomes a warning, never an alias to mutable artifact head.

NODE-54 does not pretend to be the Infinite Canvas. It preserves exact artifact identity and defines the NODE-55 selection handoff:

```json
{
  "selected_node_ids": ["hero", "headline"],
  "design_document_version": 17
}
```

## Tests and static gates added

- API public projection hides raw state/interrupt payload;
- API safe-event schema rejects recursive private reasoning;
- event replay preserves Last-Event-ID cursor;
- browser safe-event parser rejects private payload keys;
- selected node serialization pins exact DesignDocument version;
- SSE parser handles split chunks and replay dedupe;
- reducer dedupes repeated event ids;
- artifact UI requires exact ArtifactVersion identity;
- static validator locks tenant scope, safe events, stale approval, cancellation copy, selected-node handoff, and no local/session storage token state.

## Not claimed complete

NODE-54 remains validating until the P0 gaps in `reports/nodes/NODE-54/gap-ledger.json` are closed. In particular, this branch does not falsely claim production durable event replay, AgentRun→LangGraph start composition, or browser E2E evidence if those compositions/runners have not executed.
