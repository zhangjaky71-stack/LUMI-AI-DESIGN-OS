# NODE-71 — Runtime Image Supply-Chain Closure — Release Evidence

> Evidence date: 2026-08-21  
> Branch: `release-closure-p0`  
> Source hardening head: `ebacfa712899f285ffd4c6c20f2bdf7c80c5f82e`  
> Status: **SOURCE-CLOSED / HOSTED EXECUTION NOT PROVEN / NODE-71 NOT ACCEPTED**

## Decision

The code-addressable runtime-image supply-chain gap is now closed from immutable build inputs through NODE-71 frozen binding. This evidence does **not** claim a current RC was actually built, pushed, attested, frozen, accepted in Staging, or promoted to Production.

The release verdict remains:

```text
NODE-71: BLOCKED
NODE-72: BLOCKED
NODE-73: NOT ACCEPTED
```

## Closed source chain

```text
exact release-closure-p0 Git SHA
→ six remote Git contexts pinned to that SHA
→ resolve approved uv/Python base tags once to registry SHA-256 identities
→ inject the same digest-only base image pair into all six builds
→ exact service Dockerfile + linux/amd64
→ BuildKit max SLSA v0.2 provenance + SPDX SBOM
→ live provenance verifier
→ six-runtime attestation report
→ runtime_image_set.py second-line rich provenance validation
→ require all six runtimes share the same exact base-image digest pair
→ freeze common base image identities + attestation report SHA-256
→ NODE-71 Staging runtime-image binding revalidates downloaded report
→ NODE-71 passed decision seals the report SHA/source/build-run identity
→ NODE-72 revalidates that decision seal before exact-digest promotion
```

## Immutable Git source and build recipe

Canonical release builds use:

```text
context: https://github.com/${GITHUB_REPOSITORY}.git#${GITHUB_SHA}
```

for all six runtimes and reject `context: .` / `{{defaultContext}}` release regression.

The live verifier requires each actual BuildKit provenance summary to prove:

```text
buildType == https://mobyproject.org/buildkit@v1
source_uri == https://github.com/<owner>/<repo>.git#<RC_SHA>
source_digest == <RC_SHA>
entrypoint == <service Dockerfile>
platform == linux/amd64
```

## Digest-pinned base-image inputs

All six runtime Dockerfiles accept:

```text
UV_BASE_IMAGE
PYTHON_BASE_IMAGE
```

The canonical release workflow resolves the approved tags once and supplies digest-only references to every runtime build:

```text
ghcr.io/astral-sh/uv@sha256:<digest>
python@sha256:<digest>
```

The verifier requires these exact approved repositories and immutable reference form in BuildKit provenance build args. It also requires non-empty materials with SHA-256 dependency identities.

The Dockerfile tag-valued ARG defaults remain only for local developer ergonomics. Release builds are source-gated to override them with the resolved digest-only values.

## Frozen-set second-line validation

Commit `b0c2df7` hardened `scripts/runtime_image_set.py` so NODE-71 freeze no longer trusts only `build_type` and `builder_id` from the live-verifier report.

For each runtime it independently revalidates:

- canonical BuildKit build type;
- non-empty builder identity;
- exact repository + RC SHA source URI;
- exact RC source digest;
- exact frozen `build_recipe_ref` / Dockerfile;
- exact `linux/amd64` platform;
- exact approved digest-only `UV_BASE_IMAGE` / `PYTHON_BASE_IMAGE` keys;
- positive material count;
- positive SHA-256 material identity count;
- valid SPDX version and non-negative package count.

It additionally requires all six runtime provenance summaries to carry **the same exact base-image dictionary**. The normalized common pair is persisted inside frozen `attestation_verification.base_images` together with the report SHA-256.

This prevents a mixed-baseline image set from being frozen even if six individual image attestations each look valid in isolation.

## Negative contract drills

Commit `3132af6` expanded `scripts/validate_runtime_image_set_contract.py` to cover 15 fail-closed drills, including:

- missing runtime fragment;
- mutable runtime image tag;
- provenance SHA swap;
- mixed build-run provenance;
- missing/failed attestation report;
- attestation image swap;
- stale source digest;
- mixed per-runtime GitHub attestation policy;
- wrong BuildKit Git source URI;
- wrong BuildKit Dockerfile entrypoint;
- mutable base-image input;
- mixed base-image identity across runtimes;
- missing material SHA-256 identity;
- invalid SPDX package count.

## NODE-71 downloaded binding compatibility

Commit `36519ee` upgraded `scripts/validate_staging_runtime_image_binding.py` for the richer frozen schema.

The binding now:

1. requires frozen `attestation_verification.base_images`;
2. derives the exact six `build_recipe_ref` values from the frozen runtime provenance set;
3. re-runs `runtime_image_set.validate_attestation_report()` against the downloaded attestation report with those recipes;
4. requires frozen common base-image metadata to equal the normalized report result;
5. continues binding the exact report bytes by SHA-256, repository, RC SHA, requested build-run id, version and six-image set.

Its self-test now blocks frozen base-image swaps, per-runtime base-image swaps and BuildKit source URI swaps in addition to the prior digest/SHA/version/artifact/provenance/report-policy drills.

The NODE-71 decision binding schema remains unchanged intentionally. `attestation_report_sha256` cryptographically commits the complete rich report—including all six runtime base-image inputs—while the existing source SHA/build-run/artifact identities remain part of the sealed `runtime_image_binding` and resealed `decision_id`. NODE-72 already validates this exact sealed field set.

## Dedicated workflow wiring

Commit `ebacfa7` upgraded `.github/workflows/runtime-image-closure-contract.yml` so changes to `scripts/validate_staging_runtime_image_binding.py` trigger Runtime Image Closure and the job directly:

```text
compileall scripts/validate_staging_runtime_image_binding.py
python scripts/validate_staging_runtime_image_binding.py --self-test
```

Staging Acceptance and Final Acceptance already execute/syntax-gate this same binding path. The runtime-image supply-chain closure is therefore not an isolated library change.

## Relevant source commits

```text
15b0d588ea074b501de1a8d428fc647f73ededba  exact BuildKit Git-source provenance checks
c5ea993956f65a664ec589fa5622f0be8b57bc1d  SHA-pinned remote Git build contexts
9388984516602c3102d985797b51ad188b910bd9  immutable-Git build anti-regression contract
6751ed57f6c74a02b482cabc18404be27b12a24a  API base-image parameterization
0e3f5e23a491100f4f7406fdf08d471338fc8437  Agent Runtime base-image parameterization
b820f9e8a3f8ce00ac55f1de0b1ecd84e17bc78f  Model Gateway base-image parameterization
93132b8565d80a66b21a4a08309a5b06927dde55  Tool Gateway base-image parameterization
0dda8b352d746ba1c2b5deb602ce0217061e158c  Worker Media base-image parameterization
c3c8bd18bf4de7500b9a8cb6c0ff8af6b5582eab  Sandbox Runtime base-image parameterization
7925e5d167b6e2710aca6fe694edbf595f60e8d9  digest-only base-image provenance verification
8128f8e0643e15a5993498a768ed684926328556  resolve base digests once + reuse across six builds
9cbfad30af4ead45401e72a01fa750928c0aff5d  immutable Git/base-image static recipe guard
b0c2df7                                     frozen rich provenance + common base-image validation
3132af62d01ce66e8ce01b03a75322703432a0cf  frozen-set negative contract drills
36519ee56b1db1244e08a4ca6b5ad1bc74a0a826  NODE-71 downloaded binding rich-provenance compatibility
ebacfa712899f285ffd4c6c20f2bdf7c80c5f82e  dedicated Runtime Image Closure wiring
```

## Hosted CI evidence at source hardening head

Sampled head: `ebacfa712899f285ffd4c6c20f2bdf7c80c5f82e`.

```text
Runtime Image Closure Contract
run_id: 32463726227
runtime-image-closure job_id: 96715809694
failure / logs_url=null / steps=null

Staging Acceptance Gate
run_id: 32463726157
source-contract job_id: 96715810173 -> failure / logs_url=null / steps=null
canonical-lock-gate job_id: 96715810482 -> failure / logs_url=null / steps=null
contract-gate job_id: 96715825750 -> failure / logs_url=null / steps=null
remote-read-only-preflight -> skipped
acceptance-decision -> skipped

Production IaC Contract
run_id: 32463726629
terraform-static job_id: 96715812297 -> failure / logs_url=null / steps=null
source-contract job_id: 96715812547 -> failure / logs_url=null / steps=null
contract-gate job_id: 96715849697 -> failure / logs_url=null / steps=null

Final Product Acceptance Gate
run_id: 32463726703
canonical-lock-gate job_id: 96715812434 -> failure / logs_url=null / steps=null
source-contract job_id: 96715812607 -> failure / logs_url=null / steps=null
node73-final-contract-gate job_id: 96715860679 -> failure / logs_url=null / steps=null
final-decision -> skipped
```

These are zero-step GitHub-hosted runner failures. No checkout, Python, `uv`, Docker, base-image resolution, registry attestation, BuildKit provenance validation, Terraform, Staging or Production command is evidenced as having executed. Therefore these red jobs are neither source/test failures nor PASS evidence.

## Remaining runtime blockers

- resolver-generated root `uv.lock` covering all 17 workspace packages;
- real execution of the source/frozen dependency gates;
- actual resolution of the approved base-image tags to registry digests;
- actual six-runtime build and push from the exact RC SHA;
- real GitHub artifact attestation verification;
- real BuildKit provenance and SPDX SBOM retrieval;
- frozen image-set/report artifact from the exact build run;
- real NODE-71 sealed `passed=true` Production-like Staging decision;
- Terraform/Staging/Production execution;
- deployed private Model Gateway and image/video execution paths;
- live Provider benchmarks;
- rollback/DR and final approval evidence.

## Explicit non-claim

Sandbox Runtime still runs `apt-get install ffmpeg` against Debian repositories at build time. The actual final image digest and SPDX SBOM will capture the resulting installed package set, but fully snapshot-pinned OS package repositories are **not** claimed by this closure. That remains a separate reproducibility hardening opportunity and does not replace the missing runtime evidence above.
