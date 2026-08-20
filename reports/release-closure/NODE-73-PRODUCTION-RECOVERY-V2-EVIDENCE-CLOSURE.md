# NODE-73 — Production Recovery V2 Evidence Closure

## Status

**SOURCE IMPLEMENTED / RUNTIME NOT YET PROVEN**

This closure hardens the existing real Production disaster-recovery rehearsal rather than introducing a duplicate producer. It connects the existing isolated RDS PITR + object recovery runtime producer to a V2-compatible, provenance-bound, immutable recovery evidence bundle consumed by the Final Acceptance package assembler.

Final release verdict remains **KEEP NODE-73 FINAL ACCEPTANCE BLOCKED**.

## Existing real runtime producer retained

`.github/workflows/production-dr-rehearsal.yml` remains the canonical runtime producer and performs real Production recovery operations under the protected `production` environment:

- verifies the current Production six-service runtime still matches the deployment manifest Source RC;
- restores the Production RDS instance by point-in-time recovery to a new private isolated RDS instance;
- preserves the canonical DB subnet group/security boundary and sets `--no-publicly-accessible`;
- executes `scripts/production-recovery-db-verify.py` inside the accepted API task definition with Fargate `assignPublicIp:"DISABLED"`;
- verifies the isolated database in a read-only transaction, Alembic head, data invariants and workload inventory;
- measures the launch policy of database PITR RPO <= 5 minutes and RTO <= 60 minutes;
- rehearses versioned object corruption/recovery and cross-region replica recovery;
- deletes the temporary RDS target and requires source/recovery evidence versions and delete markers to return to zero;
- produces a canonical `production-recovery-decision.py` decision and archives the raw runtime evidence.

No claim is made that this runtime rehearsal has executed successfully for the current release.

## Finalization Identity V2 correction

The old recovery workflow assumed `workflow HEAD == manifest Source RC`, and the old freeze workflow also required `DR run head_sha == Source RC`. That is incompatible with NODE-73 Finalization Identity V2, where Source RC and Evidence Head are intentionally distinct identities.

The corrected contract is:

- the manual workflow executes from `release-closure-p0` at an Evidence Head;
- the Production manifest freezes the Source RC;
- Source RC must be a Git ancestor of the DR producer Evidence Head;
- the deployed Production runtime and accepted API task still bind exactly to the manifest Source RC;
- the successful DR producer head must be an ancestor of the later recovery-freeze Evidence Head;
- no recovery producer requires Source RC and Evidence Head to be equal.

`production-dr-rehearsal.yml` now checks out exact `${{ github.sha }}` with full history and disabled persisted credentials in both code-consuming jobs.

## Immutable Action supply chain

`production/release-actions/pins-v1.json` now separates:

- `release_critical_workflows`: exactly the canonical nine release executors, still bound to the default-branch release registry;
- `release_evidence_workflows`: four P0 evidence producers/freezers:
  - Staging Database Parity collector;
  - Staging Database Parity freeze;
  - Production DR Rehearsal;
  - Production Recovery Evidence freeze.

`validate_release_action_pins.py` validates both sets against the same approved immutable Action SHA allowlist while preserving the nine-workflow executor registry invariant.

The two Recovery workflows now use full approved Action commit SHAs with version annotations.

## Recovery freeze hardening

`.github/workflows/freeze-production-recovery-evidence.yml` is now a two-phase workflow.

### `validate-freeze`

Permissions: `contents: read`, `actions: read`.

It:

- checks out exact Evidence Head with full ancestry and no persisted credentials;
- resolves the canonical Production manifest and Source RC;
- requires a successful `Production DR Rehearsal` run from this repository;
- binds exact workflow name **and** `.github/workflows/production-dr-rehearsal.yml` path;
- binds event, status, conclusion, `release-closure-p0`, run ID/attempt, run URL and producer head SHA;
- proves `Source RC -> producer Evidence Head -> freeze Evidence Head` ancestry;
- downloads the exact named artifact from the exact DR run ID;
- requires exactly the five raw recovery evidence files plus the producer decision;
- verifies the producer decision is PASS and matches deployment/Source RC;
- materializes the five raw files into the canonical frozen recovery directory;
- freezes `source-run.json` from the live GitHub Actions producer metadata;
- independently recomputes the frozen recovery decision so its `evidence_refs` and `decision_id` bind the frozen repo paths rather than the producer runtime paths;
- runs the frozen recovery bundle validator;
- uploads a same-run validated freeze artifact.

### `commit-freeze`

Permission: `contents: write` only.

It does not run recovery, Terraform, AWS, GitHub cross-run lookup, recovery decision logic or recovery validators. It only:

- downloads the same-run validated freeze package;
- requires exactly seven files: `decision.json`, `source-run.json`, and five raw evidence files;
- refuses non-identical overwrite of an existing deployment recovery directory;
- checks the live remote `release-closure-p0` head still equals the dispatch SHA;
- stages only the recovery directory;
- uses a non-force push.

The write token is injected only into the final commit step.

## Frozen recovery bundle validator

`scripts/validate_frozen_production_recovery_evidence.py` requires:

- canonical manifest and recovery directory paths;
- exact deployment and Source RC identity;
- `passed=true` recovery decision;
- canonical producer repository/workflow name/workflow path;
- `workflow_dispatch`, completed/success, `release-closure-p0`, positive run ID/attempt and exact run URL;
- Source RC ancestry to producer head and producer-head ancestry to the expected Evidence Head;
- exactly seven files in the frozen bundle;
- exactly five recovery evidence refs;
- full canonical recomputation of the recovery decision from the frozen raw bytes, including every evidence path/hash and `decision_id`.

Its producer-provenance self-test contains 8 negative drills.

## Final package consumption

`.github/workflows/assemble-final-acceptance.yml` now runs the frozen recovery bundle validator before `final-acceptance-assembler-v2.py`.

The assembler therefore cannot consume a generic `passed=true` recovery JSON unless the canonical sibling `source-run.json`, frozen raw evidence set, exact hashes and recomputed decision are all valid.

`scripts/validate_production_recovery_evidence_workflow_contract.py` locks the end-to-end source contract:

- V2 Source-RC/Evidence-Head split;
- private RDS PITR and private Fargate verifier markers;
- cleanup requirements;
- immutable Action pins;
- two-phase freeze permissions;
- source-run provenance;
- 8 frozen-provenance negative drills;
- Final Assembler ordering and binding;
- four-workflow evidence pin policy while retaining exactly nine release executors.

`scripts/validate_final_acceptance_assembler_workflow_v2.py` executes this Recovery contract, and `validate_finalization_v2_contract.py` already executes the assembler workflow contract. Therefore NODE-73's V2 source-contract chain reaches the Recovery anti-regression contract without adding a parallel finalization path.

## Dispatch discovery

Fail-closed default-branch discovery stubs were added on `main` for:

- `Production DR Rehearsal` — main commit `1ddf7f7ebe9ca1f10f12e270dae1987891e5fcd4`;
- `Freeze Production Recovery Evidence` — main commit `e529f68f108dde0e8047ea1fbdcc252e1feee6be`.

They expose only the dispatch input schema, use `contents: read`, contain no external Actions/secrets/environment/write capability, and exit 64. Real execution must explicitly use `ref=release-closure-p0`.

These evidence producer stubs are intentionally not counted among the canonical nine release executor registry entries.

## Latest hosted Actions observation

At code head `bfc2baa30f47abeaa5bd7f6514ce1dcac22a4c66`:

- Final Product Acceptance Gate run `32353323396`: `canonical-lock-gate`, `source-contract`, and `node73-final-contract-gate` fail with `steps=null` / `logs_url=null`; `final-decision` is skipped.
- Staging Acceptance Gate run `32353323236`: `source-contract`, `canonical-lock-gate`, and `contract-gate` are zero-step failures; preflight and acceptance decision are skipped.
- Runtime Image Closure Contract run `32353323330`: `runtime-image-closure` is a zero-step failure.
- Recovery Contract run `32353323400`: `source-contract` is a zero-step failure and `local-destructive-drill` is skipped.

No checkout, Python, Git, uv, Terraform, AWS, PostgreSQL or application/recovery command is evidenced as having executed in these jobs. These failures are not runtime recovery failures and are not PASS evidence. No rerun was triggered.

## Still required for runtime closure

- GitHub-hosted runner execution recovery;
- canonical `uv.lock` regeneration and frozen all-workspace sync;
- successful Production deployment/canary evidence for the exact Source RC;
- an actual successful `Production DR Rehearsal` run from `ref=release-closure-p0` under the protected Production environment;
- actual isolated RDS PITR, database verifier, RPO/RTO, object recovery and cleanup PASS evidence;
- successful Recovery freeze and committed provenance-bound seven-file bundle;
- complete remaining Final Acceptance upstream evidence;
- strong live branch governance, eligible human approvals, and successful Final Decision V2.

## Verdict

**PRODUCTION RECOVERY PRODUCER = SOURCE IMPLEMENTED AND V2-COMPATIBLE**

**PRODUCTION RECOVERY FREEZE/FINAL CONSUMPTION = SOURCE IMPLEMENTED**

**PRODUCTION RECOVERY RUNTIME = NOT YET PROVEN**

**KEEP NODE-73 FINAL ACCEPTANCE BLOCKED**
