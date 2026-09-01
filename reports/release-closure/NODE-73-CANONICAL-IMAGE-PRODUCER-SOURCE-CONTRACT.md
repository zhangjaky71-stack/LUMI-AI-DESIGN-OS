# NODE-73 Release Closure — Canonical Image Producer Source Contract

Date: 2026-08-20
Repository: `zhangjaky71-stack/LUMI-AI-DESIGN-OS`
PR: `#135` — `release: close NODE-73 code-addressable P0 gates`
Branch: `release-closure-p0`
Source-contract head: `ddb20684e5e452165d4d813da9eae9d898ad0434`

## Status

`IMPLEMENTED -> VALIDATING -> BLOCKED_EXTERNAL`

This report closes only the **source-level proof gap** for the canonical product/control-plane image-generation producer. It does not claim deployed runtime PASS and does not change the NODE-73 Final Acceptance verdict.

## What is now machine-gated

`scripts/validate_image_generation_producer_contract.py` requires all of the following to remain true:

1. `apps/api/src/lumi_api/product_app.py` installs `GenerationRuntimeGateway` around the production `ApiV1Gateway` using the production `session_factory`.
2. `/api/v1/generations` is an idempotent API route and delegates to `gateway.create_generation(...)`.
3. `GenerationRuntimeGateway.create_generation(...)` enforces `project.write`, opens one database transaction, and delegates to `ImageGenerationControlPlane` with the authenticated organization and request trace.
4. `ImageGenerationControlPlane` materializes or binds the canonical `Task`, requires `image.transform`, writes the versioned `image_generation_spec` envelope, creates the canonical `Generation`, stages the dispatch outbox, and only then marks the NODE-20 idempotency operation succeeded.
5. `media_dispatch.py` rejects any task envelope whose exact fields are not `schema_version`, `job_kind`, and `image_generation_spec`, and emits the canonical `lumi.jobs.image.transform` / `lumi.media.image` dispatch.
6. PostgreSQL acceptance source asserts exactly one canonical Task, Generation, outbox dispatch and idempotency record, including the exact task kind and queue/task-name contract.
7. Worker Media reads `tasks.type/input_json`, consumes `image_generation_spec`, and validates task/org/project/operation identity before execution.

The contract is wired into `.github/workflows/final-acceptance-gate.yml` `source-contract`, and the file is also included in the workflow Python syntax compilation gate.

## Commits

- `ac4d235d0a4536433d4c4e4b8494bd5f925cd652` — add canonical image producer source contract.
- `ddb20684e5e452165d4d813da9eae9d898ad0434` — require the producer source contract in Final Product Acceptance.

## Current Hosted CI evidence

The new head triggered current Actions, but the relevant jobs still fail before executing any step.

### Image Generation

Run: `32324739899`

- `image-generation-contract` job `96293611692`: `failure`, `steps=null`, `logs_url=null`.
- `image-generation-quality`: skipped.
- `worker-media-image-smoke`: skipped.
- `image-generation-integration`: skipped.
- `image-generation-benchmark`: skipped.

### Final Product Acceptance Gate

Run: `32324739948`

- `source-contract` job `96293611966`: `failure`, `steps=null`, `logs_url=null`.
- `canonical-lock-gate` job `96293612139`: `failure`, `steps=null`, `logs_url=null`.
- `final-decision`: skipped.
- `contract-gate`: failure as a consequence of the required upstream jobs not succeeding.

No checkout, Python command, `uv`, pytest, Docker build, PostgreSQL command or application command is evidenced as having executed in those failed jobs. Therefore these runs are neither product-test failures nor PASS evidence. They remain consistent with the existing GitHub-hosted runner/account/scheduling/billing blocker.

## What remains P0-blocked

The source-level producer is now explicitly guarded, but Final Acceptance must remain BLOCKED until auditable evidence proves all runtime boundaries, including:

- canonical `uv lock` regeneration and `uv sync --all-packages --frozen`;
- execution of the new producer source contract on a trusted runnable environment;
- real PostgreSQL producer/idempotency/outbox acceptance;
- Worker Media image build/start and real `image.transform` execution;
- deployed API -> outbox -> broker -> Worker Media -> private Model Gateway path;
- proof that deployed Agent Runtime and Worker Media hold no Provider credential path;
- exact six-image build/promotion/SBOM/provenance evidence;
- Production-like Staging, Production canary, rollback and DR acceptance.

## Release verdict

**KEEP NODE-73 FINAL ACCEPTANCE BLOCKED.**

This change narrows the remaining gap from “producer existence is unproven” to “producer runtime/deployment execution evidence is unproven.” Do not mark PR #135 ready, do not declare NODE-73 accepted, and do not declare Production GO-LIVE until the remaining external and runtime evidence gates have auditable PASS results.
