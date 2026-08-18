# NODE-57 Acceptance — Agent Timeline

Status: **CORE IMPLEMENTED / VALIDATING / NOT COMPLETE**

## Implemented acceptance evidence

- [x] Timeline item model is structured by run/task/tool/progress/approval/artifact/error/status rather than generic text bubbles.
- [x] Canonical Current Stage recovers from `RunControlSnapshot` independently of browser event memory.
- [x] Frontend now preserves canonical `task_id` for task identity/observability.
- [x] Existing SSE consumer handles split chunks, Last-Event-ID and replay dedupe.
- [x] Reducer deduplicates event IDs again before Timeline insertion.
- [x] Tool actions are semantic allowlisted labels; arbitrary raw payload is never rendered.
- [x] Progress visual appears only for explicit valid integer `current/total` counts.
- [x] Retry/provider fallback is displayed only from explicit public fields.
- [x] Optional cost/credits display is sourced only from explicit public numeric fields.
- [x] Approval is anchored in sticky canonical Current Stage and continues to use NODE-54 stale resume fencing.
- [x] Artifact action exists only for an exact `artifact_id + artifact_version_id` and opens that exact Canvas version.
- [x] API schema recursively rejects private reasoning and secret-like keys.
- [x] Browser parser independently rejects private reasoning and secret-like keys before reducer ingestion.
- [x] Timeline projector ignores unrelated payload fields even if they are otherwise public.
- [x] Stable error code may be shown; stack traces are never rendered.
- [x] Dedicated Python/TypeScript tests and static acceptance validator exist.

## Hosted CI evidence — 2026-08-18

- Stacked PR: **#124**, `feat/node-57-agent-timeline` → `feat/node-56-layers-inspector`.
- NODE-57 workflow run: **32096297505**.
- `timeline-contract` job: **95588215047**, conclusion `failure`, with **zero executed steps**.
- Job log retrieval returned **404 BlobNotFound**.
- `timeline-web` job: **95588226838**, skipped because its dependency never entered executable steps.
- The same commit simultaneously produced pre-step failures for CI, Secret Scan, Dependency Review and multiple earlier NODE workflows.

This is hosted-runner/account infrastructure failure evidence, not an executed NODE-57 test/typecheck/lint/build failure. NODE-57 therefore remains **NOT COMPLETE** and must be rerun when GitHub can allocate executable steps.

## Required before COMPLETE

- [ ] Production durable `AgentEventReplayPort` composition and full refresh-history proof.
- [ ] Standardized producer-side safe event semantics for retry/fallback/progress/cost/error actions.
- [ ] Independent canonical TaskGraph history projection or equivalent durable history acceptance.
- [ ] Browser E2E for refresh, reconnect, approval, retry/fallback, artifact jump, cancellation and failure.
- [ ] Production fixture review proving nominally public summaries contain no secrets/confidential raw payload.
- [ ] Hosted GitHub Actions with executed green steps.

NODE-57 remains **NOT COMPLETE** until all P0 gaps in `gap-ledger.json` are closed with evidence.