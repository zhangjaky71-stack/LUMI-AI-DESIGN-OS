# NODE-60 Acceptance — Export Product UX

Status: **CORE IMPLEMENTED / VALIDATING / NOT COMPLETE**

## Implemented acceptance evidence

- [x] Export UI is a product client of NODE-49 Export Engine, not a second renderer/job store.
- [x] Every candidate is an exact ArtifactVersion; the currently viewed historical version is never replaced by latest/HEAD.
- [x] Capability is evaluated by exact snapshot + authorization and is rechecked when the Job is created.
- [x] Current public formats match the runtime enum only: ORIGINAL, PNG, JPEG, MP4, PDF, PPTX.
- [x] Current same-format renderer exposes ORIGINAL plus the matching source format only.
- [x] WebP/SVG and unimplemented resize/quality/alpha/print/AI-Adapt controls are not exposed.
- [x] A real Project Core export Task is created before ExportJob creation.
- [x] ExportJob creation verifies Task → Project ownership.
- [x] Idempotency-Key is used as the persistent NODE-49 operation identity.
- [x] Multiple exact versions use deterministic ZIP packaging through `force_zip`.
- [x] Product Job/read/cancel/download routes are tenant scoped.
- [x] Public outputs/package/Manifest omit bucket/storage_key.
- [x] UI follows the actual runtime Job enum: PLANNED, QUEUED, RENDERING, PACKAGING, READY, FAILED, CANCELLED, EXPIRED.
- [x] READY download signs on demand through `issue_download`; re-signing does not rerender the READY package.
- [x] Package checksum/size and Manifest exact ArtifactVersion/checksum/renderer provenance are visible.
- [x] Copy-through path is described as “No AI generation fee” without claiming zero storage/egress cost.
- [x] Whole-job failure is represented honestly; no fake per-item retry button is shown.
- [x] Python/TypeScript tests, runtime contract and explicit P0 gap ledger are present.

## Required before COMPLETE

- [ ] Cross-format transcoding and WebP/SVG.
- [ ] Resize/custom/2x/quality/alpha/crop/social presets.
- [ ] AI Adapt flow that creates a new canonical DesignVersion before export.
- [ ] Verified DPI/CMYK/bleed/crop-mark print pipeline.
- [ ] Complete cost estimate including storage/egress/transcoder/adaptation where applicable.
- [ ] Per-item batch failure and retry state.
- [ ] Project-scoped ExportJob list/activity and reopen after refresh.
- [ ] Production request-scoped ExportEngine factory composition proof.
- [ ] Browser/PostgreSQL/worker E2E.
- [ ] Hosted GitHub Actions with executed green steps.

NODE-60 remains **NOT COMPLETE** until every open P0 gap in `gap-ledger.json` has executable evidence.
