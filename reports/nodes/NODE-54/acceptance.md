# NODE-54 Acceptance Record

Status: **IMPLEMENTED / VALIDATING / NOT COMPLETE**

## Submitted implementation evidence

- real Project Core AgentRun creation/get/cancel usage;
- tenant-scoped business requests using validated session organization id;
- canonical NODE-28 control projection endpoint;
- sanitized interrupt identities with raw state/payload excluded;
- safe-event SSE endpoint with Last-Event-ID and no proxy buffering;
- API + browser recursive private-reasoning rejection;
- reconnecting fetch/ReadableStream SSE client with event dedupe and bounded backoff;
- canonical state refetch after stream end plus periodic refresh;
- exact ArtifactVersion-only artifact admission;
- selected node + exact DesignDocument version handoff for NODE-55;
- stale approval fence against current resume_version + interrupt identity;
- truthful cancellation semantics for already accepted provider side effects;
- responsive Agent / Artifact Stage / Inspector UI;
- API/browser deterministic tests and static validator.

## Hosted CI evidence

Stacked PR: `#121` (`feat/node-53-projects-ui` ← `feat/node-54-ai-workspace`).

First NODE-54 workflow execution:

```text
run id: 32090582518
workflow: NODE-54 AI Workspace
head: 712eca586c79bf300b76c9ddfc5270476335c070
conclusion: failure

workspace-contract job id: 95571801757
workspace-contract conclusion: failure
workspace-contract steps: []
workspace-contract logs: BlobNotFound / HTTP 404

workspace-web job id: 95571816417
workspace-web conclusion: skipped
workspace-web steps: null
```

No checkout, Python install, uv sync, static validator, pytest, Node setup, pnpm install, Vitest, TypeScript, ESLint, or Next.js build step executed. The same head simultaneously registered pre-run failures across repository CI and multiple NODE workflows. This is infrastructure evidence, not a NODE-54 code-test failure, and does not satisfy the Definition of Done.

## Completion blockers

See `reports/nodes/NODE-54/gap-ledger.json`. NODE-54 must not be marked COMPLETE until the P0 durable replay/control composition, browser E2E, and real Hosted CI execution evidence are closed. Applicable NODE-55/NODE-62 P1 integration items remain explicitly deferred rather than mocked.
