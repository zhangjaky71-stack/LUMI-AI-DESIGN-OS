# NODE-73 Release Closure — NODE-71 Frozen Runtime Image Build Binding

Date: 2026-08-20
Repository: `zhangjaky71-stack/LUMI-AI-DESIGN-OS`
PR: `#135`
Branch: `release-closure-p0`
Source head before this report: `61f6c501e395cad91539b7ac8e49382ce0f83c45`

## Status

`SOURCE BINDING IMPLEMENTED -> VALIDATING -> RUNTIME EVIDENCE PENDING`

This tranche closes a code-addressable release-identity gap between the six-runtime RC build workflow and NODE-71 Staging Acceptance. It does not claim that a six-image build has executed successfully or that NODE-71 has accepted a Release Candidate.

## Problem closed at source level

Before this tranche, NODE-71 required an immutable six-image set inside the completed staging evidence, but the Staging Acceptance workflow accepted only an `evidence_path`. That left a manual handoff risk: a human or automation could copy image digests/provenance from the wrong build run into the evidence document.

The Staging Acceptance workflow now requires both:

- the completed staging evidence JSON; and
- `runtime_image_set_run_id`, the exact GitHub Actions run that produced the frozen six-runtime RC image set.

NODE-71 cannot execute its acceptance decision unless both are supplied.

## Exact artifact identity

The acceptance job reads `release_candidate.git_sha` from the staging evidence and derives exactly one artifact name:

`runtime-image-set-<40-character RC SHA>`

It then downloads that artifact from exactly the requested GitHub Actions run using `actions/download-artifact@v8`, repository-scoped `GITHUB_TOKEN`, and the explicit run id.

The job requires exactly one top-level `container-image-set.json` in the downloaded artifact before any NODE-71 decision logic executes.

## Binding validator

`scripts/validate_staging_runtime_image_binding.py` requires all of the following:

1. frozen artifact schema is `LUMI_RUNTIME_IMAGE_SET_V1`;
2. evidence RC SHA equals frozen artifact RC SHA;
3. evidence RC version equals frozen artifact RC version;
4. frozen `build_run_url` is a canonical `https://github.com/<owner>/<repo>/actions/runs/<positive-id>` URL;
5. the run id embedded in `build_run_url` equals the exact `runtime_image_set_run_id` requested by the NODE-71 workflow;
6. `release_candidate.container_image_set_ref` exactly identifies that build run, artifact name, RC SHA, and `container-image-set.json`;
7. evidence `container_image_set` is byte-structure-equivalent to the frozen artifact's image set;
8. the existing NODE-71 `validate_container_image_set` accepts the frozen set;
9. normalized NODE-71 output is exactly the frozen image set;
10. exactly six immutable image refs and six provenance records exist.

This deliberately reuses the existing NODE-71 image-set validator rather than defining a parallel acceptance truth.

## Negative drills

The binding self-test requires BLOCK for:

- one image digest swapped;
- RC SHA swapped;
- RC version swapped;
- `container_image_set_ref` swapped;
- one provenance reference swapped;
- requested GitHub Actions run id swapped;
- frozen artifact `build_run_url` swapped;
- non-canonical build-run URL containing query/fragment or wrong URL shape.

## Workflow anti-regression contract

`scripts/validate_staging_runtime_image_workflow_contract.py` statically requires:

- `runtime_image_set_run_id` workflow input;
- `actions: read` permission;
- binding self-test in `source-contract`;
- exact cross-run artifact download through `actions/download-artifact@v8`;
- artifact name derived from evidence RC SHA;
- positive decimal run-id validation before download;
- one exact `container-image-set.json` after extraction;
- `--expected-run-id` passed to the binding validator;
- artifact download and binding to execute before `staging-acceptance-gate.py`.

The same binding self-test and workflow contract are also wired into Final Product Acceptance's `source-contract` so NODE-73 cannot silently regress this NODE-71 release-identity boundary.

## Commits in this tranche

- `eadbe5f34643c5afa8561b7a76af717ffacdc028` — initial NODE-71 frozen image-set binding validator.
- `e8bebc7d1230036739a7bf5a2312eee7a39913c7` — exact requested build-run id and canonical run-URL binding.
- `539f888bb0b19aacae4d46cb75ebe4192218c8fb` — NODE-71 workflow anti-regression validator.
- `6b59555a1afceccf32ed33ebe5b18d532fcb561c` — Staging Acceptance cross-run artifact download and binding integration.
- `606e39a98744caef593768e3999edd77a9294e82` — align static workflow contract with implemented artifact derivation.
- `61f6c501e395cad91539b7ac8e49382ce0f83c45` — Final Product Acceptance binding self-test integration.

## Current Hosted status

At source head `61f6c501e395cad91539b7ac8e49382ce0f83c45`:

### Staging Acceptance Gate

Run `32326034537` currently reports:

- `source-contract` job `96297352627`: queued, no executed steps yet;
- `canonical-lock-gate` job `96297352818`: queued, no executed steps yet;
- `acceptance-decision`: skipped because the PR event did not supply workflow-dispatch evidence/run-id inputs.

### Final Product Acceptance Gate

Run `32326034506` currently reports:

- `source-contract` job `96297352440`: queued, no executed steps yet;
- `canonical-lock-gate` job `96297352157`: queued, no executed steps yet;
- `final-decision`: skipped because this is not a completed manual acceptance invocation.

Queued jobs are not PASS evidence. The repository also continues to show the historical Hosted Runner pattern where many jobs fail before steps start, so successful execution must still be observed before any runtime claim is made.

## Remaining runtime P0

This binding makes the future acceptance path deterministic, but the following evidence is still required:

1. canonical `uv.lock` regeneration with the pinned resolver;
2. frozen all-workspace dependency install;
3. successful execution of the six-runtime build/push/attest workflow;
4. registry-resolvable exact digests for all six images;
5. actual SBOM and provenance attestations for those exact digests;
6. successful NODE-71 workflow dispatch with a completed evidence JSON plus the exact runtime-image build run id;
7. Production-like Staging deployment of the frozen digests;
8. successful environment parity and P0 scenario evidence;
9. NODE-72 deployment of exactly the NODE-71-accepted image set;
10. Production canary, rollback, and DR evidence.

## Release verdict

**KEEP NODE-73 FINAL ACCEPTANCE BLOCKED.**

The release identity path is now source-closed as:

`one RC SHA -> one six-image build run -> one immutable artifact -> one NODE-71 evidence image set -> one frozen NODE-71 decision -> exact NODE-72 deployment`

Execution evidence for that chain remains pending, so PR #135 stays Draft and this is not Production GO-LIVE approval.
