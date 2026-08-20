# NODE-73 Release Closure — End-to-End RC Identity Chain

Date: 2026-08-20
Repository: `zhangjaky71-stack/LUMI-AI-DESIGN-OS`
PR: `#135`
Branch: `release-closure-p0`
Source head before this report: `df1a40ae24a174209fff43154a51e50770a0d3b1`

## Status

`SOURCE IDENTITY CHAIN IMPLEMENTED -> VALIDATING -> HOSTED EXECUTION BLOCKED`

This tranche closes the remaining code-addressable release-identity handoff gaps from immutable runtime image construction through NODE-71 Staging Acceptance and NODE-72 Production deployment. It does not claim a successful build, Staging acceptance, Production deployment, rollback, DR rehearsal, or Final Acceptance.

## Canonical release identity chain

The source contract now enforces one directed identity chain:

`RC Git SHA`

→ `one six-runtime Build and Freeze RC Runtime Image Set workflow run`

→ `runtime-image-set-<RC SHA>` artifact

→ exactly six `image@sha256:<digest>` identities with SBOM/provenance/source paths

→ `NODE-71 Staging Acceptance` exact build-run artifact download

→ staging evidence `container_image_set` exact equality with the frozen build artifact

→ `NODE-71 decision.json`

→ `NODE-71 decision-provenance.json` binding decision SHA-256 + run ID + run URL + repository + decision_id + RC identity

→ `NODE-72 Deploy Production` exact NODE-71 run artifact download

→ Production manifest exact `staging_acceptance_run_id` binding

→ exact NODE-71 RC SHA/version/migration/image-set equality

→ Production Terraform variables for the exact six accepted immutable images.

There is no longer a source-supported manual digest handoff or manual NODE-71 decision-file input in the production deployment workflow.

## Six-runtime build identity

The existing Release Closure now contains:

- `production/runtime-images/manifest-v1.json` — exactly six production runtimes;
- `.github/workflows/build-runtime-image-set.yml` — one RC build/push/attest/freeze workflow;
- `scripts/runtime_image_set.py` — NODE-71-compatible immutable image-set assembler;
- `scripts/validate_runtime_image_build_pipeline.py` — build pipeline anti-regression contract;
- `scripts/validate_runtime_image_set_contract.py` — positive/negative image-set drills.

Every build is preceded by canonical workspace lock checks and frozen all-workspace installation. Every runtime image uses an immutable digest for acceptance, with SBOM and provenance references attached to the frozen set.

## NODE-71 build-artifact binding

`Staging Acceptance Gate` now requires both:

- completed staging evidence JSON; and
- exact `runtime_image_set_run_id`.

The acceptance job derives `runtime-image-set-<RC SHA>` from the evidence itself, downloads it from that exact Actions run, and validates:

- RC SHA equality;
- RC version equality;
- exact requested run-id equality with the artifact `build_run_url`;
- exact `container_image_set_ref`;
- exact six-image/provenance structure equality;
- existing NODE-71 image/provenance rules.

The binding implementation and anti-regression contracts are:

- `scripts/validate_staging_runtime_image_binding.py`;
- `scripts/validate_staging_runtime_image_workflow_contract.py`.

## NODE-71 decision provenance

A passing NODE-71 decision now produces `decision-provenance.json` before artifact upload.

`scripts/validate_node71_decision_artifact.py` records and verifies:

- schema/kind;
- repository;
- workflow name;
- exact positive GitHub Actions run ID;
- canonical run URL with the same run ID;
- `decision.json` SHA-256;
- decision ID;
- release-candidate identity.

Only `passed=true` NODE-71 decisions can receive a decision provenance record. The Staging workflow self-verifies the decision/provenance pair before archival.

Negative drills block:

- requested run-ID swap;
- repository swap;
- decision-content/SHA swap;
- run-URL swap.

## NODE-72 exact NODE-71 artifact consumption

The Production deployment workflow no longer accepts an `acceptance_decision_path` input.

It now accepts `staging_acceptance_run_id` and:

1. requires a positive decimal run ID;
2. requires the production manifest to contain the same `staging_acceptance_run_id`;
3. requires canonical `staging_acceptance_path = reports/production-deployments/runtime/node71/decision.json`;
4. downloads `staging-acceptance-decision` from exactly that Actions run;
5. requires exactly one top-level `decision.json` and `decision-provenance.json` pair;
6. verifies NODE-71 workflow provenance;
7. invokes `production-deployment-gate.py` with decision, provenance, exact run ID, and repository;
8. only after the gate passes exports immutable release metadata to the protected Production job.

The production gate itself also fails closed on:

- missing/PENDING/zero NODE-71 run identity;
- any non-canonical/manual acceptance path;
- manifest run-ID mismatch with the requested run;
- invalid decision provenance;
- NODE-71 `passed != true`;
- RC SHA/version/migration mismatch;
- any of the six Production image digests differing from the NODE-71 accepted set.

Anti-regression contract:

- `scripts/validate_production_node71_workflow_contract.py` rejects reintroduction of manual decision paths or removal/reordering of the exact cross-run artifact/provenance gates.

## Final Acceptance integration

The Final Product Acceptance `source-contract` now runs all of the release-identity contracts before a Final Acceptance decision can ever be evaluated:

- canonical image producer source contract;
- six-runtime manifest/build/freeze contracts;
- runtime image-set negative drills;
- NODE-71 frozen build-artifact binding drills;
- NODE-71 workflow anti-regression contract;
- NODE-71 decision artifact provenance drills;
- NODE-72 production workflow anti-regression contract;
- Production deployment contract drills;
- existing Tool Gateway provenance contracts.

The Final Acceptance canonical lock gate remains independent and mandatory.

## Key commits in this identity closure

### Six-runtime RC build/freeze

- `541eb47d9d441ff594283e8853c9d3f4bbb049e0`
- `00415faad292c709e381fc3341c4a505b4949d8c`
- `78fe065e672111eaadcb8271c55c1b4771747b13`
- `a7b8aa949108b1fc4b4222cf896214f00de364a3`
- `0e2ea254636e3fcdc848338d9e7edd42a7646bc6`

### NODE-71 frozen image-set binding

- `eadbe5f34643c5afa8561b7a76af717ffacdc028`
- `e8bebc7d1230036739a7bf5a2312eee7a39913c7`
- `539f888bb0b19aacae4d46cb75ebe4192218c8fb`
- `6b59555a1afceccf32ed33ebe5b18d532fcb561c`
- `606e39a98744caef593768e3999edd77a9294e82`
- `61f6c501e395cad91539b7ac8e49382ce0f83c45`

### NODE-71 decision provenance / NODE-72 exact artifact handoff

- `4d41094bbf41f0d5a234b766b984204c669ee22f`
- `431eb042f711315208cb55093aacf5f23ad3bd8d`
- `8a244d072c2068ffe1650b2b11244a3b3307c9c7`
- `106c2627af47b2428ad529137e3abed41a134541`
- `ec8a89760003030c4be0e0641fd942ee06c444fb`
- `c07d7b77fec29dc05d95ae32bb008af75f0b3d3e`
- `ba276b81157615fc3ba71df17c0289a5a9b2ce8c`
- `3e3d0a2cea722a7de9c1ddacfea6deb03260df9e`
- `507c7841e081f20d697d8083c2f06fe47c41d1b0`
- `df1a40ae24a174209fff43154a51e50770a0d3b1`

## Latest Hosted CI observation

At head `df1a40ae24a174209fff43154a51e50770a0d3b1`, the newly wired gates are triggered but the GitHub-hosted environment continues to exhibit the established pre-step failure pattern.

### Production IaC Contract — run `32326424487`

- `source-contract` job `96298496728`: `failure`, `steps=null`, `logs_url=null`;
- `terraform-static` job `96298496532`: `failure`, `steps=null`, `logs_url=null`;
- `contract-gate`: failure as a consequence.

### Staging Acceptance Gate — run `32326424480`

- `source-contract` job `96298496616`: `failure`, `steps=null`, `logs_url=null`;
- `canonical-lock-gate` job `96298496835`: `failure`, `steps=null`, `logs_url=null`;
- read-only preflight and acceptance decision: skipped on the PR event;
- `contract-gate`: failure as a consequence.

### Final Product Acceptance Gate — run `32326424423`

- `source-contract` job `96298496448`: `failure`, `steps=null`, `logs_url=null`;
- `canonical-lock-gate` job `96298496543`: `failure`, `steps=null`, `logs_url=null`;
- `final-decision`: skipped on the PR event;
- `contract-gate`: failure as a consequence.

No checkout, Python, uv, Terraform, Docker, artifact download, registry, attestation, PostgreSQL, or application command is evidenced as having executed in these failing jobs. These red statuses therefore remain neither application-test failures nor PASS evidence.

## Remaining P0 execution blockers

The release identity handoff is now source-closed, but Final Acceptance remains blocked until trusted execution proves:

1. canonical `uv.lock` regeneration using the pinned resolver;
2. `uv sync --all-packages --frozen` across every workspace package;
3. real PostgreSQL migration/ORM drift/idempotency/cost/image-generation suites;
4. successful six-runtime build/push/SBOM/provenance workflow;
5. registry-resolvable exact six-image digest set;
6. successful Production-like Staging deployment of those exact images;
7. successful NODE-71 acceptance using the exact build-run artifact;
8. successful NODE-72 Production deployment using the exact NODE-71 run artifact;
9. canary/readiness/runtime-identity evidence;
10. rollback and disaster-recovery rehearsals;
11. final Production smoke and operational approvals.

## Release verdict

**KEEP NODE-73 FINAL ACCEPTANCE BLOCKED.**

The codebase now has a deterministic, provenance-bound RC identity path with no source-supported manual image/decision substitution at the NODE-71/NODE-72 handoffs. Runtime execution of that path remains unproven because Hosted jobs are still failing before steps start. PR #135 must remain Draft and this work is not Production GO-LIVE approval.
