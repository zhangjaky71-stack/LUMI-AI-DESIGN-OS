# NODE-73 Release Action Supply-Chain Pins

Status: **IMPLEMENTED -> VALIDATING -> BLOCKED_EXTERNAL**

Scope: NODE-73 Release Closure only. This evidence does not introduce NODE-74 and does not change the Final Acceptance verdict.

## P0 finding

The release identity chain had already frozen application dependencies, six runtime image digests, image provenance, NODE-71 artifact identity, and NODE-72 decision provenance, but release-critical GitHub Actions were still referenced through movable major-version tags such as `@v6`, `@v7`, and `@v4`.

That left a supply-chain drift window before immutable runtime artifacts were produced or accepted.

## Implemented closure

### Canonical allowlist

Added `production/release-actions/pins-v1.json` with policy `LUMI_RELEASE_ACTION_PINS_V1`.

The allowlist currently records 11 external Action repositories and 12 approved version/SHA pairs. `actions/upload-artifact` deliberately has two approved immutable releases because the runtime-image producer uses v7 while existing release evidence workflows remain on v4; this avoids an unrelated major-version migration during NODE-73 closure.

Every approved ref is a full lowercase 40-character commit SHA and carries its human-readable version separately.

### Fail-closed validator

Added `scripts/validate_release_action_pins.py`.

For every workflow listed by `release_critical_workflows`, the validator requires each external `uses:` line to satisfy all of the following:

1. `owner/repository@<full 40-character SHA>` form.
2. Lowercase hexadecimal SHA40, not a tag, branch, or short SHA.
3. Exact approved `# vX.Y.Z` annotation.
4. Action repository present in the canonical allowlist.
5. SHA/version pair present in the canonical allowlist.

Built-in negative drills require the following to block:

- floating version tag;
- abbreviated SHA;
- missing version annotation;
- unknown SHA;
- unknown Action repository.

### Release-critical workflow coverage

The policy covers exactly these NODE-73 release-chain workflows:

- `.github/workflows/build-runtime-image-set.yml`
- `.github/workflows/regenerate-uv-lock.yml`
- `.github/workflows/runtime-image-closure-contract.yml`
- `.github/workflows/staging-acceptance-gate.yml`
- `.github/workflows/production-iac-contract.yml`
- `.github/workflows/deploy-production.yml`
- `.github/workflows/final-acceptance-gate.yml`

### High-privilege self-gates

The two high-impact mutation producers fail closed on the pin policy inside their own manually dispatched workflow, not only through PR validation:

- `regenerate-uv-lock.yml` validates the pin policy before `uv lock` can mutate and commit `uv.lock`.
- `build-runtime-image-set.yml` validates the pin policy before GHCR login, package writes, image attestations, or runtime-image artifact publication.

`deploy-production.yml` also validates the pin policy in `release-gate` before downloading the cross-run NODE-71 artifact and before any production release metadata can reach the OIDC/AWS/Terraform mutation job.

### Existing anti-regression contracts upgraded

- `validate_runtime_image_build_pipeline.py` now requires exact approved Action SHAs, six pinned build actions, six pinned attestation actions, and verifies the pin self-check occurs before registry login.
- `validate_staging_runtime_image_workflow_contract.py` now requires exact pinned upload/download Actions and requires NODE-71 source validation to execute the pin policy.
- `validate_production_node71_workflow_contract.py` now requires the exact pinned cross-run download Action and enforces ordering: action-pin gate -> NODE-71 artifact download -> provenance validation -> production deployment gate -> release metadata export.
- Runtime Image Closure, Production IaC Contract, NODE-71 Staging Acceptance, and NODE-73 Final Acceptance execute the common pin validator in their source-contract path.

## Source audit at this checkpoint

Current branch source was re-fetched after the changes and searched for floating `@v...` Action references.

Result: **0 floating `@v...` references** across all seven release-critical workflows.

This is a source-level audit only. It is not presented as hosted execution PASS evidence.

## Commits in this closure slice

- `0fd9414a546138bb32550f90886321bcdb964367` — canonical Action pin allowlist.
- `7dede2599685567a8c824d88d3e25e27e75b02c0` — fail-closed pin validator + negative drills.
- `1ce87874b0d46a1fc94200168e1eee7dedd59914` — canonical uv-lock regeneration self-gate.
- `333f83b7da4fcbb18c477495c5c93294fa40c837` — six-runtime build/freeze self-gate.
- `a6120731a327448872e75b22a56058f403ce7cd0` — runtime-image pipeline exact-pin/order contract.
- `3e40e9dd5d7c27a73f3b2cdb74156aaf8dad68ec` — Runtime Image Closure pin gate integration.
- `161d1079dd59f54559eabd595a36f67d3befea89` — NODE-71 workflow immutable Action pins.
- `565d9d36b2007494a7f22610963e4d1390f1ca47` — NODE-71 pin-aware anti-regression contract.
- `29ca1ce1e7173d5238a3bb1f33da803f80f06ecd` — Production IaC immutable Action pins.
- `3b3ed25dc9bab61914b60a260c0352382eaf285c` — Production deploy immutable Action pins and pre-download self-gate.
- `300904fec82e27c46a01223e777e002d6b9a4df1` — NODE-72 pin-aware anti-regression contract.
- `14627874993c89802f80b9af46e61e10cabe1ea7` — Final Acceptance pin gate integration.
- `811f8061099d4d51d7089cfaa6e7217566a4174c` — initial immutable Action supply-chain evidence checkpoint.

## Hosted CI observation

Sampled code/evidence head: `811f8061099d4d51d7089cfaa6e7217566a4174c`.

The release-critical PR workflows were accepted by GitHub and runs were created, but the relevant jobs again failed before an executable step was materialized:

- Runtime Image Closure run `32328063266`: job `96303247731` (`runtime-image-closure`) -> `failure`, `steps=null`, `logs_url=null`.
- Staging Acceptance run `32328063284`: jobs `96303247896` (`canonical-lock-gate`) and `96303248016` (`source-contract`) -> `failure`, `steps=null`, `logs_url=null`; dispatch-only acceptance/preflight jobs were skipped as expected for a PR run.
- Production IaC Contract run `32328063310`: jobs `96303247880` (`source-contract`) and `96303247978` (`terraform-static`) -> `failure`, `steps=null`, `logs_url=null`.
- Final Product Acceptance run `32328063252`: jobs `96303247762` (`canonical-lock-gate`) and `96303247927` (`source-contract`) -> `failure`, `steps=null`, `logs_url=null`; `final-decision` was skipped as expected for a PR run.

No checkout, Python interpreter setup, `validate_release_action_pins.py`, `uv`, Terraform, Docker, PostgreSQL, or application command is evidenced as having executed in those jobs.

Therefore these hosted red jobs are **not** interpreted as release-action pin contract failures and are **not** PASS evidence. They remain consistent with the established GitHub-hosted runner/account/scheduling/billing blocker.

## What is not claimed

This closure does **not** claim that GitHub-hosted runners executed the validator, Docker builds, attestations, Terraform validation, Staging acceptance, or Production deployment.

It also does not repair the stale canonical `uv.lock`; that still requires a real `uv lock` execution followed by `uv sync --all-packages --frozen` in a trusted runnable environment.

Remaining external/runtime evidence blockers continue to include PostgreSQL acceptance, six-runtime image build/start/attestation evidence, Production-like Staging, live sandbox egress probes, NODE-71/NODE-72 runtime evidence, Production smoke/canary/rollback/DR, and final approvals.

## Verdict

**KEEP NODE-73 FINAL ACCEPTANCE BLOCKED.**

This P0 closes a code-addressable release Action supply-chain drift window. NODE-73 can only advance when trusted execution produces auditable PASS evidence for the still-blocked runtime gates.
