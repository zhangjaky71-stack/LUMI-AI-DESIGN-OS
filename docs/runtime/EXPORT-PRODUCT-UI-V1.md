# Export Product UI Runtime Contract V1

Status: NODE-60 core implementation contract.

## Canonical authority

The product UI is a client of NODE-49 Export Engine and Project Core. It does not own export formats, ArtifactVersion approval, renderer capability, package state, Manifest data, or download authorization.

Every export item identifies an **exact ArtifactVersion**. No product path resolves `latest` or silently switches to a branch head.

## Current renderer capability

The runtime `ExportFormat` enum is:

- ORIGINAL
- PNG
- JPEG
- MP4
- PDF
- PPTX

The currently composed renderer is verified same-format copy-through. `ORIGINAL` always means checksum-verified exact source copy. A named format is available only when the exact source MIME is the matching format and a renderer declares the target format.

The current ExportRequestItem has only:

- artifact_version_id
- target_format
- output_name

Therefore resize, custom dimensions, scale, quality, alpha, crop, social presets, WebP, SVG, print settings and AI Adapt are not product capabilities yet.

## Capability check

`GET /api/v1/projects/{project_id}/artifact-versions/{version_id}/export-capabilities`:

1. snapshots the exact version through NODE-49 `snapshot_exact`;
2. requires APPROVED snapshot state;
3. performs export authorization for the authenticated actor;
4. returns only actual source-MIME-compatible formats;
5. returns unsupported feature flags as false.

Capabilities are rechecked when the ExportJob is created to prevent stale client claims.

## Task and Job attribution

Before creating an ExportJob, the product creates a real Project Core Task with `task_type=export` and exact ArtifactVersion IDs in task input.

ExportJob creation validates that the supplied Task belongs to the same Project. The request `Idempotency-Key` must be a UUID and becomes NODE-49 `operation_id`, so repeated semantically identical creation can use the existing export idempotency contract.

## Job states

The actual runtime enum is:

- PLANNED
- QUEUED
- RENDERING
- PACKAGING
- READY
- FAILED
- CANCELLED
- EXPIRED

The UI must never invent PENDING or VALIDATING states.

## Product-safe Job projection

The public product response contains:

- exact ArtifactVersion item IDs and requested target format/output name;
- output filename/MIME/size/checksum/renderer version/exact source IDs;
- package filename/MIME/size/checksum/archive flag;
- Manifest exact version/checksum/renderer/operation/exporter data;
- job status/error code.

It does not contain bucket or storage_key.

## Batch packaging

When more than one exact version is selected, the client requests `force_zip=true`. NODE-49 builds the deterministic package/Manifest. The current runtime fails the overall job on render or packaging failure; there is no per-item retry state model, so the UI must not pretend partial retry exists.

## Download grants

Download is permitted only for READY packages. Every Download click calls NODE-49 `issue_download(job_id, actor_id)` to get a fresh signed grant. Re-signing does not rerender or rebuild the READY package.

The browser allows HTTPS signed URLs and local HTTP only for localhost development. Signed URLs are not persisted into the ExportJob UI state beyond the immediate navigation; only the expiry timestamp is retained for display.

## Cost language

The current verified copy-through path does not call an AI generation provider, so the UI may say “No AI generation fee.” It must not claim zero total cost or invent storage/egress/transcoder amounts without a real cost estimate contract.

## AI Adapt and Print

AI Adapt is not an export transform. Future support must create a new canonical DesignVersion through a recipe/Agent flow before export.

Print DPI, CMYK, bleed and crop marks stay hidden until NODE-49 has a verified color-management/render contract.

## Known gaps

- cross-format transcoding / WebP / SVG;
- resize, quality, alpha, crop and social presets;
- AI Adapt recipe + new DesignVersion flow;
- verified print/color-management options;
- complete cost estimate;
- per-item batch failure/retry;
- durable list/reopen/export activity after page refresh;
- production export_engine_factory composition proof;
- browser/PostgreSQL/worker E2E;
- hosted executed-green CI.
