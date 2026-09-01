# NODE-73 Runtime Image Signer / Source Identity Closure

Status: **IMPLEMENTED -> VALIDATING -> BLOCKED_EXTERNAL**

Scope: NODE-73 Release Closure only. This evidence does not introduce NODE-74 and does not change the Final Acceptance verdict.

## P0 finding

The six-runtime RC pipeline already required immutable image digests, GitHub artifact attestation verification, BuildKit SLSA provenance, SPDX SBOMs, a hashed `attestation-verification.json`, and NODE-71 binding of that report to the frozen image set.

The remaining source-level trust gap was that `gh attestation verify` was scoped only to the repository. A valid attestation produced by another workflow in the same repository could therefore satisfy the repository-level actor check unless the signer workflow and source revision were also constrained.

## Authoritative GitHub CLI semantics

The GitHub CLI attestation verifier exposes the following independent policy controls:

- `--signer-workflow`: constrains the certificate SAN to the specified workflow path.
- `--source-digest`: constrains the certificate `SourceRepositoryDigest` extension.
- `--source-ref`: constrains the certificate `SourceRepositoryRef` extension.
- `--deny-self-hosted-runners`: constrains the certificate runner environment to GitHub-hosted runners.

GitHub CLI's policy implementation maps these values directly into Sigstore/Fulcio certificate enforcement criteria. This closure therefore uses certificate-backed identity fields rather than trusting workflow-authored SLSA predicate metadata for the release source identity.

## Implemented closure

### Runtime verifier identity gate

`scripts/verify_runtime_image_attestations.py` now derives a fail-closed `GitHubAttestationPolicy` from the GitHub Actions runtime environment.

Normal verification requires:

- repository: the exact `GITHUB_REPOSITORY` supplied by the canonical build workflow;
- source digest: exact lowercase SHA40 from `GITHUB_SHA`;
- source ref: exactly `refs/heads/release-closure-p0`;
- signer workflow: exactly `<OWNER>/<REPO>/.github/workflows/build-runtime-image-set.yml`;
- workflow ref: exactly `<OWNER>/<REPO>/.github/workflows/build-runtime-image-set.yml@refs/heads/release-closure-p0`;
- runner trust: `--deny-self-hosted-runners`.

Each of the six image verification calls now executes `gh attestation verify` with all of:

- `--repo <OWNER/REPO>`;
- `--signer-workflow <OWNER/REPO>/.github/workflows/build-runtime-image-set.yml`;
- `--source-digest <GITHUB_SHA>`;
- `--source-ref refs/heads/release-closure-p0`;
- `--deny-self-hosted-runners`.

A single mismatch prevents the verifier from writing a PASS report.

### Self-describing immutable evidence

Both the top-level attestation report and each runtime result now record the exact signer/source policy used for verification:

- `signer_workflow`;
- `source_digest`;
- `source_ref`;
- `workflow_ref`;
- `deny_self_hosted_runners`.

The existing release closure already SHA-256 binds the entire `attestation-verification.json` into `LUMI_RUNTIME_IMAGE_SET_V1`, so these new identity fields are transitively frozen into the NODE-71 image-set artifact without introducing a second identity document.

### Negative drills

The verifier self-test now requires these source-identity mutations to BLOCK:

- malformed/non-SHA40 `GITHUB_SHA`;
- wrong source branch/ref;
- wrong signer workflow path in `GITHUB_WORKFLOW_REF`.

Existing immutable image-ref, BuildKit provenance, and SPDX SBOM negative drills remain in place.

### Anti-regression gate

`scripts/validate_runtime_image_build_pipeline.py` now statically requires the verifier to retain:

- canonical release source ref constant;
- canonical signer workflow path constant;
- `GITHUB_SHA`, `GITHUB_REF`, and `GITHUB_WORKFLOW_REF` runtime checks;
- `--signer-workflow`, `--source-digest`, `--source-ref`, and `--deny-self-hosted-runners` flags;
- signer/source policy fields in the persisted attestation report;
- source-level negative identity drills.

The release `source-gate` already runs both the verifier self-test and build-pipeline contract before any package/attestation write capability is granted.

## Commits

- `675df92729b3dbd6c29b324f10d3c3624c6c4f63` — bind live runtime image attestation verification to signer workflow, source SHA/ref, and GitHub-hosted runner identity.
- `ebf34963f5585d4dace8dc10574114317bb09f47` — add source anti-regression requirements for signer/source identity enforcement.

## What is not claimed

This closure does not claim that a Hosted runner has successfully executed the stricter `gh attestation verify` command against six promoted images.

The checked-in canonical `uv.lock` is still stale, and the currently observed hosted-runner failure mode has historically prevented checkout/step execution. Real six-runtime build/push/attestation verification remains external runtime evidence that must be produced before NODE-73 can pass.

## Verdict

**KEEP NODE-73 FINAL ACCEPTANCE BLOCKED.**

The code-addressable signer/source identity ambiguity is closed. Advancement still requires trusted execution evidence for the canonical dependency graph, image build, attestation verification, Staging/NODE-71/NODE-72, PostgreSQL/Terraform, and Production gates.
