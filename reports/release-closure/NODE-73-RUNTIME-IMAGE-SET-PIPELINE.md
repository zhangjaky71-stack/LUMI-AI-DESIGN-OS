# NODE-73 Release Closure — Six-Runtime RC Image Set Pipeline

Date: 2026-08-20
Repository: `zhangjaky71-stack/LUMI-AI-DESIGN-OS`
PR: `#135`
Branch: `release-closure-p0`
Source head: `dea812d8ab186822f71c0223c4e056087eb8612a`

## Status

`SOURCE PIPELINE IMPLEMENTED -> VALIDATING -> BLOCKED_EXTERNAL`

This tranche closes the code-addressable gap that previously had no single process for building and freezing all six Production runtime images as one Release Candidate set. It does not claim that the images have actually built, been promoted, deployed, or accepted.

## Canonical runtime set

`production/runtime-images/manifest-v1.json` defines exactly these six runtime units:

1. `api`
2. `agent-runtime`
3. `model-gateway`
4. `tool-gateway`
5. `worker-media`
6. `sandbox-runtime`

Each entry binds a production Dockerfile, executable entrypoint, and source-provenance paths. API, Model Gateway, and Worker Media source lists are checked against the existing NODE-71 Staging Acceptance required-source sets, so this does not create a second provenance contract.

## Build and freeze workflow

`.github/workflows/build-runtime-image-set.yml` is an explicit `workflow_dispatch` Release Closure workflow restricted to branch `release-closure-p0`.

Before any registry mutation it requires:

- exact branch/head checkout;
- clean worktree;
- `scripts/validate_uv_workspace_lock.py`;
- pinned `uv 0.11.28`;
- `uv lock --check`;
- `uv sync --all-packages --frozen`;
- six-runtime source closure validation;
- runtime-image manifest validation.

Only after those gates pass does the workflow authenticate to GHCR and build the six images.

For every image the workflow requires:

- root repository build context;
- the canonical production Dockerfile;
- `linux/amd64` output;
- registry push;
- RC SHA tag for discoverability only;
- BuildKit `provenance: mode=max`;
- BuildKit `sbom: true`;
- GitHub `actions/attest@v4` provenance bound to the exact image digest and pushed to the registry.

The mutable RC tag is never used as acceptance identity. The workflow resolves and verifies all six registry digests and freezes only `image@sha256:<64 hex>` references.

## NODE-71-compatible image-set assembler

`scripts/runtime_image_set.py`:

- validates the exact six-runtime manifest;
- validates declared source paths exist;
- validates Dockerfiles still use Python 3.12, canonical frozen all-workspace install and UID/GID 10001;
- requires immutable digest references;
- records build recipe, entrypoint, SBOM reference, provenance reference and exact source paths;
- requires every fragment to share one exact Git SHA and one build-run URL;
- assembles exactly six runtime fragments;
- reuses `staging-acceptance-gate.py::validate_container_image_set` before emitting the final image set.

Therefore the frozen artifact is already shaped to the NODE-71 acceptance contract rather than requiring a second translation layer.

## Negative drills

`scripts/validate_runtime_image_set_contract.py` creates a synthetic six-image set and requires the following drills to block:

- one runtime fragment missing;
- mutable image tag instead of `@sha256`;
- provenance Git SHA swapped;
- one image originating from a different build-run identity.

`scripts/validate_runtime_image_build_pipeline.py` statically rejects workflow regressions including:

- missing one of the six runtimes;
- missing canonical lock gates;
- missing GHCR push;
- missing max provenance;
- missing SBOM;
- missing registry attestation;
- introduction of a `latest` tag;
- failure to freeze build-step digests;
- failure to upload the final six-runtime set.

Both validators are wired into Runtime Image Closure and Final Product Acceptance source gates.

## Commits in this tranche

- `541eb47d9d441ff594283e8853c9d3f4bbb049e0` — canonical six-runtime manifest.
- `00415faad292c709e381fc3341c4a505b4949d8c` — runtime image-set assembler.
- `78fe065e672111eaadcb8271c55c1b4771747b13` — six-runtime build/push/attest/freeze workflow.
- `a7b8aa949108b1fc4b4222cf896214f00de364a3` — build-pipeline anti-regression validator.
- `dc10b1a139ff903f3e1e974423dad172761c5e7c` — Runtime Image Closure integration.
- `7ecda559acf13980044330f64f8b91dc0d31745f` — Final Acceptance integration.
- `0e2ea254636e3fcdc848338d9e7edd42a7646bc6` — image-set positive/negative self-test.
- `8e690b1a0f7f58f9636da3e1f8db0c1562905002` — Runtime Image Closure self-test wiring.
- `dea812d8ab186822f71c0223c4e056087eb8612a` — Final Acceptance self-test wiring.

## Hosted CI observation

At head `dea812d8ab186822f71c0223c4e056087eb8612a`:

### Runtime Image Closure Contract

Run `32325693104`:

- `runtime-image-closure` job `96296345925`: `failure`, `steps=null`, `logs_url=null`.

### Final Product Acceptance Gate

Run `32325693086`:

- `source-contract` job `96296346351`: `failure`, `steps=null`, `logs_url=null`;
- `canonical-lock-gate` job `96296346427`: `failure`, `steps=null`, `logs_url=null`;
- `final-decision`: skipped;
- `contract-gate`: failure because required upstream jobs did not succeed.

No checkout, Python, uv, Docker, GHCR, BuildKit, attestation or application command is evidenced as having executed. These runs are not application-test failures and are not PASS evidence.

The manual `Build and Freeze RC Runtime Image Set` workflow has not been dispatched because the currently available GitHub connector does not expose workflow-dispatch creation, and the repository's Hosted Runner remains unable to start ordinary jobs anyway.

## Remaining P0

The source-level six-image process now exists, but NODE-73 must remain BLOCKED until evidence proves:

1. canonical `uv.lock` regenerated by the pinned resolver;
2. `uv sync --all-packages --frozen` succeeds;
3. this six-image workflow actually executes from one exact RC SHA;
4. all six images build and push successfully;
5. all six immutable digests resolve from the registry;
6. SBOM and provenance attestations exist for the exact digests;
7. the frozen image-set artifact is archived and consumed by NODE-71;
8. Production-like Staging deploys those exact six digests;
9. NODE-72 Production deploys the exact NODE-71-accepted digests;
10. canary, rollback and DR evidence passes.

## Release verdict

**KEEP NODE-73 FINAL ACCEPTANCE BLOCKED.**

The prior gap “no six-runtime build/promotion process exists” is narrowed to “the canonical six-runtime build/freeze process exists but has not executed successfully on a trusted runner.” PR #135 remains Draft and is not Production GO-LIVE approval.
