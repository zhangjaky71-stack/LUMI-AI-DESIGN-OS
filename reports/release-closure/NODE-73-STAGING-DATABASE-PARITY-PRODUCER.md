# NODE-73 — Staging Database Parity Producer Closure

## Status

**SOURCE IMPLEMENTED / RUNTIME NOT YET PROVEN**

This closure adds a real Production-like Staging producer for PostgreSQL engine-major and migration-head parity without exposing the database to GitHub-hosted runners and without allowing the resulting artifact to satisfy unrelated Staging scenarios.

Final release verdict remains **KEEP NODE-73 FINAL ACCEPTANCE BLOCKED**.

## Producer chain

1. `Collect Staging Database Parity` runs only by explicit `workflow_dispatch` on `release-closure-p0` and uses the protected `staging` environment plus OIDC.
2. The workflow checks out the exact Source RC SHA and verifies the deployed API and migration task both use the accepted immutable API image digest.
3. Terraform state is used only to resolve the canonical private Staging migration task/network and canonical PostgreSQL endpoint identity.
4. The probe runs as a one-shot Fargate task in private subnets with `assignPublicIp=DISABLED`; the database URL remains inside the migration task through the existing migration secret.
5. `lumi_api.staging_database_parity_probe` executes `alembic check`, then opens a read-only transaction and verifies PostgreSQL major version, transaction read-only mode, the single Alembic head, release identity, and canonical database-host hash.
6. The collector revalidates the structured CloudWatch result outside the task and uploads a bounded raw evidence package.
7. `Freeze Staging Database Parity` requires a successful collector run from this repository, binds Source RC ancestry and collector head provenance, recomputes the DB validator, creates a canonical `LUMI_STAGING_EVIDENCE_ARTIFACT_V1` wrapper, live-verifies the producer run, and uses a separate write-only commit phase with an exact remote-head guard and non-force push.
8. `merge_staging_database_parity_evidence.py` can consume the frozen wrapper/catalog only for `PARITY-DB` and `PARITY-MIGRATIONS`.

## Fail-closed boundaries

- No GitHub runner receives `MIGRATION_DATABASE_URL`.
- No public database route or public Fargate IP is introduced.
- The probe contains no `alembic upgrade head` path and no evidence-storage write capability.
- The collector has no `contents: write` permission.
- The write-capable freeze job cannot execute database/validator/Terraform/AWS runtime logic.
- Frozen evidence is immutable per RC/file pair and cannot be force-pushed over branch history.
- The generic wrapper binds the exact raw collector evidence SHA-256.
- The DB evidence artifact is explicitly forbidden from appearing in any `scenario_results[*].evidence_ref`; in particular it cannot make `ENV-02` PASS.
- Existing parity results and existing catalog entries cannot be overwritten implicitly.

## Executable anti-regression coverage

`validate_staging_database_parity_evidence.py` defines 8 negative drills.

`merge_staging_database_parity_evidence.py` defines 5 negative merge drills including existing-result overwrite, scenario misuse, RC swap, validation tamper, and catalog SHA swap.

`validate_staging_database_parity_contract.py` binds the probe, collector, freezer, merge boundary, pinned Actions, private-Fargate topology, two-phase freeze, and the executable negative drills.

`validate_staging_runtime_image_workflow_contract.py` executes that producer contract, so the same contract is reached by both the NODE-71 Staging source gate and NODE-73 Final source gate.

## Dispatch discovery

Fail-closed registry stubs for the DB collector and DB freeze workflow exist on `main`. They only expose the dispatch schema and exit with refusal. Real execution must explicitly use:

`ref=release-closure-p0`

These producer workflows are Staging evidence producers, not additions to the canonical nine release-critical executor registry entries.

## Latest hosted Actions observation

At PR head `e3bd1a8ee4b885baabe5f60fd43e3713658ab484`, the relevant pull-request workflows still fail before any executable step starts:

- Final Product Acceptance Gate run `32351839371`: `canonical-lock-gate`, `source-contract`, and `node73-final-contract-gate` are failures with `steps=null` and `logs_url=null`; `final-decision` is skipped.
- Staging Acceptance Gate run `32351839412`: `canonical-lock-gate` and `source-contract` are failures with `steps=null` and `logs_url=null`; remote preflight and acceptance decision are skipped; the contract gate also has no steps/logs.
- Runtime Image Closure Contract run `32351839487`: `runtime-image-closure` is a zero-step failure.
- Production IaC Contract run `32351839566`: `terraform-static`, `source-contract`, and `contract-gate` are zero-step failures.

No checkout, Python, uv, Docker, Terraform, PostgreSQL, or application command is evidenced by these jobs. They are not application-test failures and are not PASS evidence.

## Still required for runtime closure

- successful hosted runner execution;
- canonical `uv.lock` regeneration and frozen all-workspace sync;
- actual Staging DB collector execution against Production-like Staging;
- successful freeze and live producer verification;
- merge of the canonical DB wrapper into a complete NODE-71 Staging evidence package;
- the remaining parity/scenario producers needed for full Staging acceptance;
- successful NODE-71 decision and downstream NODE-72/NODE-73 evidence.

## Verdict

**STAGING DATABASE PARITY PRODUCER = SOURCE IMPLEMENTED**

**STAGING DATABASE PARITY RUNTIME = NOT YET PROVEN**

**KEEP NODE-73 FINAL ACCEPTANCE BLOCKED**
