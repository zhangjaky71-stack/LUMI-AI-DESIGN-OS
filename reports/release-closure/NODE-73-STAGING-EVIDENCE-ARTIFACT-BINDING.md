# NODE-73 — Staging Evidence Artifact + Live Producer Binding

## Status

**SOURCE/CODE-ADDRESSABLE CLOSURE IMPLEMENTED — RUNTIME VALIDATION STILL BLOCKED**

This report records the NODE-71/NODE-73 source-level closure for a P0 evidence-integrity gap in Production-like Staging acceptance. It does **not** claim that Staging, PostgreSQL, runtime images, or Final Acceptance have executed successfully.

## P0 gap closed

The generic `staging-acceptance-gate.py` historically treated a scenario/parity `PASS` as evidenced when fields such as `actual`, `owner`, and a non-empty `evidence_ref` were present. Dedicated validators existed for selected domains such as media generation and Tool Gateway provenance, but there was no universal byte-level contract proving that every generic PASS `evidence_ref` pointed to an immutable, RC-bound evidence artifact produced by a real successful run.

That left generic P0 scenarios such as environment/database parity, resilience/restore, browser, performance, security, and other acceptance checks vulnerable to a source-level evidence substitution in which an arbitrary non-empty string could satisfy the generic `evidence_ref` presence check.

## Canonical binding model

`staging/acceptance/evidence-template.json` now exposes a fail-closed `evidence_artifacts` catalog.

Every `PASS` in:

- `environment_parity`; and
- `scenario_results`

must resolve through that catalog to a JSON evidence wrapper below:

`reports/staging-acceptance/evidence/`

Each catalog entry binds:

- artifact path;
- SHA-256 of exact artifact bytes;
- exact Source RC Git SHA.

The artifact payload must additionally bind:

- schema/kind;
- logical artifact/evidence ref;
- `status = PASS`;
- Source RC SHA;
- capture timestamp;
- repository;
- producer workflow name;
- producer workflow path;
- producer GitHub Actions run id;
- producer run attempt;
- producer run URL;
- producer head SHA;
- producer head branch.

Paths are constrained below the canonical staging evidence root and symlink/path-escape attempts are rejected.

## Live producer verification

`validate_staging_evidence_artifacts.py` supports `--require-live-producers` and the canonical Staging acceptance workflow enables it.

For every distinct producer run, the validator reads the GitHub Actions run and requires the live record to match the committed artifact metadata, including:

- repository;
- workflow name;
- workflow path;
- run id;
- run attempt;
- head SHA;
- head branch;
- canonical run URL;
- `status = completed`;
- `conclusion = success`.

The ephemeral GitHub Actions read token is injected only into the `acceptance-decision` evidence-binding step. It is not workflow-scoped and is not available to source-contract, canonical-lock-gate, or remote preflight jobs.

## Exact source identity

All four NODE-71 code-consuming jobs checkout the exact `${{ github.sha }}` with `persist-credentials: false`.

The generic evidence/live-producer binding executes before:

1. exact frozen six-runtime artifact binding;
2. domain-specific Tool Gateway/media evidence validators;
3. the NODE-71 staging acceptance decision.

The binding report is archived together with NODE-71 decision artifacts under `reports/staging-acceptance/runtime/`.

## Executable anti-regression

`validate_staging_runtime_image_workflow_contract.py` now does more than inspect workflow markers. It directly executes:

`python validate_staging_evidence_artifacts.py --self-test`

and requires the self-test JSON to report:

- `status = PASS`;
- `static_negative_drills = 8`;
- `live_negative_drills = 8`;
- `verified_artifacts = 2`.

The static drills reject missing catalog entries, SHA swaps, RC swaps, path escape, artifact-id swaps, non-PASS artifacts, incomplete producer identity, and control-character logical refs.

The live drills reject non-completed/non-success producer runs and mismatches in producer head SHA, head branch, run attempt, workflow name/path, and repository.

This workflow contract is executed by both the NODE-71 Staging source gate and the NODE-73 Final source gate, so a marker-only regression cannot silently disable the validator's behavior.

## What remains unproven

This source closure is not runtime PASS evidence. The following remain blocked until trusted execution occurs:

- canonical `uv.lock` regeneration and frozen all-workspace sync;
- successful GitHub-hosted job execution;
- real PostgreSQL migration / ORM-drift / integration evidence;
- six-runtime build/start/promotion and attestation evidence;
- real Production-like Staging scenario/parity artifacts and successful producer runs;
- NODE-71 accepted staging decision;
- NODE-72 Production deployment/canary/rollback/DR proof;
- live branch protection + Evidence Head lock;
- real human approvals and V2 Final Decision `accepted=true`.

## Release verdict

**KEEP NODE-73 FINAL ACCEPTANCE BLOCKED.**
