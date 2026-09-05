# NODE-49 — Export Engine

> Phase: 6 Generation & Quality  
> Status: **IMPLEMENTED / VALIDATING / not COMPLETE**  
> Priority: P0 / PRODUCT DELIVERY  
> Depends on: NODE-40 Canvas Engine, NODE-41 Canvas Compiler, NODE-42 Artifact Engine, NODE-19 Asset Storage  
> Produces: exact-version raster/SVG/PDF/batch/LUMI package export, manifest, Artifact lineage and authorized download

---

## 1. Goal

NODE-49 converts an immutable design version into delivery-grade files. Export is not a second layout engine and never reads floating `latest` after creation.

Core invariant:

```text
ExportSpec(exact ArtifactVersion + exact DesignVersion)
  -> exact source snapshot
  -> NODE-41 compile snapshot
  -> safe render/package
  -> format validation + checksum readback
  -> NODE-42 ArtifactVersion(s)
  -> authorized short-lived download
```

## 2. Supported V1 formats

```text
PNG
JPEG
WebP
SVG
PDF
ZIP batch
LUMI project package
```

Video export remains NODE-48.

Explicit fail-closed boundaries:

```text
PSD                -> EXPORT_PSD_NOT_SUPPORTED
CMYK               -> EXPORT_CMYK_NOT_SUPPORTED_V1
Display P3         -> EXPORT_DISPLAY_P3_NOT_VERIFIED_V1
bleed/crop marks   -> EXPORT_PRINT_MARKS_NOT_IMPLEMENTED_V1
VIDEO node in SVG  -> EXPORT_VIDEO_NODE_REQUIRES_NODE_48
```

These capabilities must not be advertised as supported until a dedicated verified implementation exists.

## 3. Exact source snapshot

`ExportSourceSnapshot` pins:

- organization/project;
- Artifact + ArtifactVersion;
- exact DesignDocumentVersion;
- source content and constraint hashes;
- exact sanitized Design IR snapshot;
- NODE-41 durable render-plan snapshot;
- compiler version/hash/resource versions/font versions;
- Brand Rules version;
- rights summary;
- model/provenance references;
- optional project package metadata.

`ArtifactEngineExportSource` resolves the exact ArtifactVersion, loads the requested DesignVersion, runs `CanvasCompiler.fullCompile(..., false)`, rejects compile failure and strips ephemeral `*_uri/*_url` values before durable persistence/package creation.

Export never re-reads project latest during worker execution.

## 4. ExportSpec

```text
organization_id
project_id
requested_by
operation_id
artifact_version_id
design_document_version_id
variants[]:
  variant_id
  frame_ids[]
  format
  width/height/scale
  resize_mode = SCALE | CROP
  quality
  alpha/background
  color_profile
  dpi/unit
  bleed/crop_marks
  filename
filename_template
include_manifest
retention_seconds
```

Floating names such as `latest/head/current` are rejected.

## 5. SCALE and CROP only

NODE-49 owns only export geometry operations:

```text
SCALE -> SVG preserveAspectRatio = xMidYMid meet
CROP  -> SVG preserveAspectRatio = xMidYMid slice
```

`MM` and `IN` target dimensions convert to pixels with requested DPI. `PX` stays pixel-native.

If a 9:16 design needs a new 1:1 layout, an Agent/Layout workflow must create another DesignVersion first. `DESIGN_ADAPTATION` is forbidden inside the Export Engine.

## 6. Server rendering

Production server rendering is renderer-neutral at the SDK boundary:

```text
SafeSvgRenderPlanSerializer
  -> WorkerBackedRasterCodec
  -> RasterWorkerTransport
  -> isolated Chromium raster worker
```

The concrete worker is `scripts/export-raster-worker.mjs` and uses the root locked `@playwright/test@1.61.1` Chromium runtime.

Security/runtime rules:

- HTTP(S) routes are blocked;
- SVG external href/script is rejected;
- raster images must be trusted `data:image/png|jpeg|webp;base64` supplied by an authorized resource resolver;
- output blob is decoded again and natural dimensions must equal target dimensions;
- MIME is checked against the requested PNG/JPEG/WebP format.

No MIME relabeling is accepted as real format support.

## 7. Safe SVG

`SafeSvgRenderPlanSerializer` consumes the exact sanitized Design IR plus NODE-41 render plan.

Supported:

- FRAME/SHAPE/MASK;
- TEXT;
- IMAGE using trusted inline raster data;
- VECTOR_PATH only when exact Design IR contains `metadata.svg_path`.

Fail closed:

- unresolved/placeholder resource;
- unknown node kind;
- VIDEO node;
- missing vector geometry;
- external font/image URL;
- script/external href.

Canvas `Matrix2D` is consumed using the real `{a,b,c,d,tx,ty}` contract.

Font resolution uses embedded authorized CSS where available; otherwise text falls back explicitly to `sans-serif` rather than silently failing export.

## 8. PDF

PDF pages map to selected Frames. V1 renders each page to verified JPEG then embeds it in a deterministic PDF 1.7 writer.

Independent `inspectRasterPdf()` validates:

- PDF header;
- xref/startxref;
- EOF;
- page count;
- MediaBox dimensions.

DPI controls pixel-to-point conversion.

## 9. ZIP and LUMI package

ZIP uses a deterministic store-mode writer with:

- UTF-8 entry names;
- CRC32;
- no path traversal/drive/absolute path;
- duplicate rejection;
- local-header size/CRC validation;
- central-directory/local-header consistency;
- EOCD count/offset/size validation;
- trailing-data rejection.

Batch ZIP:

```text
files/<export files>
manifest.json
```

LUMI package:

```text
lumi/manifest.json
lumi/design-document.json
lumi/compiler-provenance.json
lumi/rights-summary.json
lumi/project-snapshot.json   # optional
lumi/exports/<export files>
```

Design/render snapshots are stripped of ephemeral runtime URLs before package creation.

## 10. Manifest

Manifest V1 includes:

- export engine version/job/fingerprint;
- project/artifact/version/design version;
- source content hash;
- compiler provenance/hash;
- semantic ExportSpec;
- output filename/MIME/checksum/size/dimensions/page count;
- source provenance refs;
- Brand Rules version;
- rights summary;
- model refs;
- created timestamp;
- manifest SHA-256.

Recursive security checks reject API keys, secrets, authorization/access/refresh/provider tokens and hidden/system prompt fields.

## 11. Job lifecycle

```text
PENDING
RENDERING
PACKAGING
VALIDATING
READY
FAILED
EXPIRED
```

`ExportEngine.start()` pins source and fingerprint. `execute()` never reloads latest design state.

Semantic reuse:

- same operation + different fingerprint -> conflict;
- existing READY fingerprint during retention -> reuse output, no rerender;
- re-download -> new signed URL only.

## 12. Persistence

Migration: `db/migrations/0008_export_engine.sql`.

Tables:

```text
export_jobs
export_files
export_format_validations
export_download_audit
```

Storage keys/checksums are durable. Signed/presigned URLs are intentionally absent from the schema.

## 13. NODE-42 Artifact integration

`ArtifactEngineExportAdapter` creates one output ArtifactVersion per exported file/manifest so multi-format/multi-size exports do not collide with ArtifactFile role uniqueness.

Each output:

- attaches a verified storage object;
- stores compiler provenance;
- records export manifest hash in file/edge metadata;
- adds `EXPORTED_FROM` exact source ArtifactVersion;
- transitions to READY only after verification.

## 14. Download API

`ExportApiFacade` exposes:

```text
createExport
runExport
getExport
getDownload
```

`ExportDownloadService` requires:

- organization-scoped READY job;
- retention not expired;
- exact file exists;
- authorization port returns allowed;
- signed URL TTL between 30 and 900 seconds.

The signer port maps to NODE-19 `S3ObjectStore.get_signed_download()` in server wiring. The signed URL is response-only and never persisted.

## 15. Tests and evidence

Executable suites:

- `export-engine-v1.test.ts` — exact pin, semantic reuse, authorization, PDF/ZIP, SCALE/CROP, units, font fallback, false-claim gates;
- `export-source-adapter.test.ts` — real NODE-41 CanvasCompiler and signed URI stripping;
- `export-artifact-adapter.test.ts` — verified NODE-42 Artifact and EXPORTED_FROM lineage;
- `export-package.test.ts` — LUMI package content + ZIP tamper detection;
- `export-benchmark.test.ts` — deterministic 100-file packaging/validation harness;
- `scripts/export-raster-worker.test.mjs` — real Chromium PNG/JPEG/WebP MIME, signature and decoded dimensions.

Conformance fixture: `fixtures/export-engine/node-49-conformance.json` (62 control/format/security cases).

Architecture validator: `scripts/validate_export_engine.py`.

## 16. Acceptance gates

- [x] exact Artifact/DesignVersion snapshot contract;
- [x] SCALE/CROP and px/mm/in conversion;
- [x] real Chromium PNG/JPEG/WebP worker implementation;
- [x] safe SVG serialization;
- [x] deterministic PDF writer + independent parser;
- [x] ZIP/LUMI package security;
- [x] manifest + SHA-256 readback;
- [x] NODE-42 Artifact lineage adapter;
- [x] authorized short-lived download contract;
- [x] database schema;
- [x] executable tests/static validator/benchmark harness;
- [ ] hosted CI actually executes green;
- [ ] real Chromium format smoke executes on hosted pinned runner;

## 17. Definition of Done

NODE-49 is COMPLETE only when:

```text
export contract/typecheck green
+ Artifact/Canvas regression green
+ real Chromium PNG/JPEG/WebP smoke green
+ PDF/SVG/ZIP tests green
+ PostgreSQL migration green
+ packaging benchmark harness green
```

A GitHub Actions zero-step account/billing failure is an external blocker, never PASS and never an observed code/test failure.

Next: **NODE-50 — Visual Critic**.
