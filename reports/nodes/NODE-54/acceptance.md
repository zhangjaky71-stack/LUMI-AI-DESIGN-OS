# NODE-54 Acceptance Evidence

> Node: AI Design Workspace  
> Status: IMPLEMENTED / VALIDATING / NOT COMPLETE  
> Base: `node-53-projects-ui-release` @ `8a4deb28df42867fa25d4687e94b7591e81c27b7`

## Implemented product surface

- `/app/projects/{projectId}/workspace` route.
- Active Workspace entry from the NODE-53 Project detail page.
- Desktop Agent / Canvas / Context workspace.
- Mobile focused Agent / Canvas / Context tabs.
- Multiline prompt composer with selected-node, document-version, reference and exact ArtifactVersion context.
- Safe realtime message model with no private reasoning fields.
- SSE reconnect contract with `Last-Event-ID`, tenant header, duplicate-event suppression and canonical refetch.
- Versioned Pause / Resume / Stop / Retry commands.
- Exact-version Artifact cards and Canvas placement.
- Embedded Approval cards with expiry/stale-run protection.
- Provider degradation/fallback warning surface.
- Deterministic non-production E2E adapter.

## Static validation

Candidate-tree execution:

```text
python scripts/validate_ai_workspace.py
NODE-54 AI Workspace validation PASSED
```

The validator checks the route, production/E2E boundary, same-origin tenant-scoped SSE, Last-Event-ID, dedupe, canonical refresh, selected-node/document-version payloads, versioned controls, stale approvals, exact Artifact placement, mobile panels, provider-warning coverage, browser persistence guardrails and private-reasoning field guardrails.

## TypeScript candidate validation

The available local environment is not the pinned repository environment. A strict compatibility check was run against the new AI Workspace runtime and unit tests using the available TypeScript 5.8.3 with repository-equivalent strict options (`strict`, `noUncheckedIndexedAccess`, `exactOptionalPropertyTypes`). No runtime/unit type errors were observed.

This is supporting evidence only. The repository pins TypeScript 6.0.3, so the hosted TypeScript gate remains authoritative.

## Local environment limitation

Available local tooling at assembly time:

```text
Node       22.16.0
npm        10.9.2
TypeScript 5.8.3
Python     3.13.5
pnpm       unavailable
Prettier   unavailable
```

The repository requires the hosted Node 24 / pnpm 11 / TypeScript 6.0.3 toolchain. Therefore no local production Next build, pinned lint/format gate or Playwright PASS is claimed.

## Hosted gate definition

`.github/workflows/ai-workspace.yml` defines:

```text
ai-workspace-contract
ai-workspace-quality
ai-workspace-build
ai-workspace-security
ai-workspace-browser-e2e
```

The browser job also reruns NODE-53 Projects and NODE-52 App Shell scenarios.

## Hosted run evidence — 2026-08-15

Draft PR #54 triggered AI Workspace run `31860047798` against implementation SHA `6f7f9506fbb747ccc2f7938e8a1b6a762dc3e238`.

Observed result:

```text
ai-workspace-contract     failure before runner start
steps                     []
runner_id                 0
ai-workspace-quality      skipped
ai-workspace-build        skipped
ai-workspace-security     skipped
ai-workspace-browser-e2e  skipped
```

GitHub's check annotation states that the job was not started because recent account payments failed or the account spending limit must be increased. Therefore this run provides no TypeScript, lint, unit, build, security or browser execution evidence and must not be classified as a code/test failure or as a PASS.

The same commit also caused CI, Secret Scan, Dependency Review, App Shell and Projects UI workflows to report failure at the platform level; NODE-54 acceptance remains blocked on actual runner execution.

## Production dependency truth

NODE-54 exposes typed HTTP/SSE contracts but does not claim completion of backend nodes merely because deterministic E2E behavior exists.

Before NODE-54 can be marked COMPLETE, the relevant production Agent control plane/realtime/Canvas/canonical API dependencies must be connected or formally superseded, and pinned hosted frontend gates must execute green.

## Current verdict

```text
AI Workspace product UI         IMPLEMENTED
safe realtime/reconnect client  IMPLEMENTED
selected-node context           IMPLEMENTED
versioned run controls          IMPLEMENTED
Artifact exact-version actions  IMPLEMENTED
Approval stale protection       IMPLEMENTED
mobile focused UX               IMPLEMENTED
static architecture gate        PASS on candidate tree
strict compatibility typecheck  PASS with local TS 5.8.3 only
pinned hosted gates             BLOCKED BEFORE RUNNER START (billing/spend limit)
production runtime integration  UPSTREAM DEPENDENCY
```

NODE-54 is **IMPLEMENTED / VALIDATING / NOT COMPLETE**.
