# NODE-73 Runtime Image Attestation Verification Closure

Status: **IMPLEMENTED -> VALIDATING -> BLOCKED_EXTERNAL**

Scope: NODE-73 Release Closure only. This evidence does not introduce NODE-74 and does not change the Final Acceptance verdict.

## P0 finding

The six-runtime RC build already produced immutable image digests, BuildKit `mode=max` provenance, BuildKit SBOM attestations, and GitHub artifact attestations. The frozen NODE-71 image set retained `sbom_ref` and `provenance_ref` strings.

However, the release chain did not require an executable proof that those attestation objects were actually resolvable and valid before the image set was frozen. A syntactically valid provenance/SBOM reference was therefore weaker than a verified registry attestation.

A second gap remained after live verification was added: the generated verification report initially lived beside `container-image-set.json` without being cryptographically bound into the frozen image-set schema consumed by NODE-71.

## Implemented closure

### Live six-runtime attestation verifier

Added `scripts/verify_runtime_image_attestations.py`.

The real build mode requires exactly these six `service=image@sha256:<digest>` inputs:

- api
- agent-runtime
- model-gateway
- tool-gateway
- worker-media
- sandbox-runtime

For each exact digest it fails closed unless all of the following succeed:

1. `docker buildx imagetools inspect <digest-ref>` resolves the registry image.
2. `gh attestation verify oci://<digest-ref> --repo <OWNER/REPO>` verifies the GitHub artifact attestation.
3. BuildKit SLSA provenance can be read with `imagetools inspect --format '{{ json .Provenance.SLSA }}'` and contains a build type, builder identity, and materials array.
4. SPDX SBOM can be read from the image index, with a documented linux/amd64 fallback, and contains the SPDX document identity/version and packages array.

The verifier records tool identity plus per-runtime results in:

`attestation-verification.json`

with schema/kind:

`LUMI_RUNTIME_IMAGE_ATTESTATION_VERIFICATION_V1`

The report can only have top-level `status: PASS` when all six runtimes pass.

### Source-level negative drills

`verify_runtime_image_attestations.py --self-test` uses no registry or GitHub network calls. It blocks:

- mutable image tags;
- short/invalid digests;
- malformed service input;
- missing BuildKit provenance fields;
- missing builder identity/materials array;
- invalid SPDX document identity/version/packages array.

The self-test is wired into the read-only runtime-image source gate, Runtime Image Closure, and NODE-73 Final Acceptance.

### Live verification must precede freeze

`build-runtime-image-set.yml` now runs the live verifier only after all six `actions/attest` steps complete and before NODE-71 image-set assembly.

The build writes the report under:

`reports/runtime-image-sets/<GIT_SHA>/attestation-verification.json`

The freeze step explicitly requires the report to exist and report `status=PASS`.

`validate_runtime_image_build_pipeline.py` now enforces the ordering:

`last image attestation -> live six-image verification -> freeze -> artifact upload`

and requires all six digest refs, repository binding, `GH_TOKEN`, report output, and the PASS barrier.

### Cryptographic report binding in frozen image set

`runtime_image_set.py assemble` now requires:

`--attestation-report <.../attestation-verification.json>`

Before creating `LUMI_RUNTIME_IMAGE_SET_V1`, it validates that the report:

- has the canonical attestation verification schema/kind;
- is `PASS` for exactly six runtimes;
- has a concrete GitHub repository identity;
- records Docker Buildx and GitHub CLI tool identity;
- contains each runtime exactly once;
- maps each verified image ref exactly to the image digest being frozen;
- records registry resolution and GitHub attestation verification as true;
- contains BuildKit provenance and SPDX SBOM summaries for every runtime.

The frozen image-set now contains an `attestation_verification` object with:

- schema/kind;
- `status=PASS`;
- `runtime_count=6`;
- repository identity;
- canonical report filename;
- SHA-256 of the exact report bytes.

### Image-set contract negative drills

`validate_runtime_image_set_contract.py` now requires a valid report during assembly and blocks:

- missing report;
- report status FAIL;
- report image/digest mismatch;
- existing mutable-image/provenance-SHA/build-run mutations.

### NODE-71 consumes and re-hashes the report

`staging-acceptance-gate.yml` now requires the downloaded six-runtime artifact to contain exactly one top-level pair:

- `container-image-set.json`
- `attestation-verification.json`

Both must parse as JSON.

`validate_staging_runtime_image_binding.py` now receives both files and recomputes SHA-256 over the downloaded report bytes. NODE-71 blocks unless:

- recomputed report SHA-256 equals the hash frozen into the image set;
- frozen report metadata has the exact canonical shape;
- report repository equals the repository encoded by the exact build-run URL;
- report schema/kind/status/runtime count are canonical;
- report six-runtime image mapping equals the frozen image digests;
- report verification/provenance/SBOM summaries remain valid;
- existing exact RC SHA/version/build-run/container-image-set identity checks also pass.

New NODE-71 negative drills block:

- report hash swap;
- report status swap;
- report image swap;
- report repository swap;
- requested run-id swap;
- frozen build-run URL swap;
- non-canonical build-run URL.

`validate_staging_runtime_image_workflow_contract.py` additionally requires the runtime artifact download -> exact two-file check -> cryptographic binding -> NODE-71 decision ordering.

## Commits

- `6ad5f6f7eb49c13b638381816b24ec13031242f1` — live runtime image attestation verifier and parser negative drills.
- `444b523591ebbd9d49eca829886463dbf5506923` — live verification step before image-set freeze.
- `38cfffd42d2dc1ca146d7810503879638936513d` — runtime-image build ordering/verification anti-regression contract.
- `34703e752c48f24c5e69986889791fc0cfcfda82` — Runtime Image Closure self-test integration.
- `b9d0ec08545f04ea93caf3d35038e680d7995806` — Final Acceptance self-test integration.
- `3c60813e1c7e89bf18bf5db4527bfd842e42a6a7` — cryptographically bind verification report into frozen image-set schema.
- `c87617f18aa8f983fd11988c9b73f5fcf13213da` — image-set attestation-report negative drills.
- `5d9c7474610b83d303f36f83d7417f4d2482e0b7` — NODE-71 downloaded-report byte/hash/repository/image binding.
- `9d3b621b43e87272a091d76f336f8b623e9c71bb` — pass attestation report into production image-set assembly.
- `e9d03c42e3444d1b8e0b6a172e0d07dd504be1fe` — require exact image-set/report pair at NODE-71 intake.
- `95fd9f019e91fac9f57ef3b2534fd62f0f35f808` — NODE-71 two-file artifact anti-regression contract.

## Source audit at this checkpoint

Current branch source was re-fetched after the changes.

Observed build-chain order:

1. six immutable images built and pushed;
2. six GitHub artifact attestations created;
3. `verify_runtime_image_attestations.py` verifies all six exact digest refs;
4. `attestation-verification.json` is persisted;
5. freeze requires report `status=PASS`;
6. assembler validates report and freezes its SHA-256 into `container-image-set.json`;
7. both files are uploaded in the same `runtime-image-set-<SHA>` artifact.

Observed NODE-71 intake order:

1. exact build run/artifact downloaded;
2. exactly one image-set JSON and one attestation report JSON required;
3. downloaded report bytes are re-hashed;
4. frozen report SHA/repository/six-image mapping is verified;
5. only then may NODE-71 evaluate Staging acceptance and produce its decision provenance.

This is source-level evidence only. It is not represented as successful registry/attestation execution evidence.

## What is not claimed

The current GitHub-hosted runner condition still prevents reliable execution of the new live verifier. No claim is made that six current RC images have already passed `gh attestation verify`, BuildKit provenance inspection, or SPDX SBOM inspection.

The canonical `uv.lock` remains stale and must still be regenerated and frozen in a trusted runnable environment before the six-image build can legitimately start.

Remaining release blockers continue to include trusted CI/PostgreSQL execution, actual six-runtime build/start/attestation evidence, Production-like Staging and network probes, NODE-71/NODE-72 runtime evidence, Production smoke/canary/rollback/DR, and final approvals.

## Verdict

**KEEP NODE-73 FINAL ACCEPTANCE BLOCKED.**

This P0 converts release image provenance from reference-only metadata into a live-verification requirement with cryptographic report binding through NODE-71, but runtime PASS still requires trusted execution.
