# NODE-73 Staging Release Operations

This directory contains the auditable request used by the `Release Staging Dispatch Bridge`.

The product release candidate is immutable and is identified by its exact `release_git_sha`. Release-orchestration commits may advance independently; they do not change the frozen runtime RC.

## Canonical operation order

1. `plan-core`
2. `apply-core`
3. `promote-runtime-images`
4. `plan-migration`
5. `apply-migration`
6. `run-migration`
7. `plan-app`
8. `apply-app`
9. collect/freeze NODE-71 evidence
10. dispatch `Staging Acceptance Gate`

`promote-runtime-images` copies the exact frozen GHCR OCI image set into Terraform-managed Staging ECR repositories with `skopeo --all --preserve-digests`. A promotion is PASS only when all six destination manifest digests exactly equal their frozen source digests.

Migration and App operations must consume the exact six-image ECR digest map emitted by the successful promotion run. Floating tags and legacy `*_IMAGE_DIGEST` repository variables are not accepted by the canonical Staging deploy workflow.

## Request file

The bridge listens only to:

```text
production/staging/release-request-v1.json
```

Every request must bind `source_parent` to the immediately preceding `release-closure-p0` commit. Mutating operations additionally require:

```json
{
  "mutation_ack": "APPLY_STAGING"
}
```

Promotion requests also bind the successful runtime-image-set build run, artifact id, and GitHub artifact digest. Migration/App requests carry the exact `promoted_image_set` object from the successful promotion artifact. App requests may also set `video_model_profile`; otherwise the Staging environment variable `VIDEO_MODEL_PROFILE` must already be configured.

A bridge issue with state `DISPATCHED` is dispatch provenance only. It is never acceptance evidence by itself.

## Acceptance boundary

None of these operations may mark NODE-71 or NODE-73 accepted. NODE-71 still requires sealed evidence and a successful canonical `Staging Acceptance Gate`. NODE-73 remains blocked until the complete production promotion/rehearsal/final-decision chain is also satisfied.
