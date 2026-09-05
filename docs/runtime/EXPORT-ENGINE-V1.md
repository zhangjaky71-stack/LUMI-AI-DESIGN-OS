# Export Engine V1 Runtime

Status: **IMPLEMENTED / VALIDATING / not COMPLETE**  
Node: NODE-49  
Owner: Artifact / Delivery runtime

## Purpose

Export Engine converts an immutable LUMI design version into reproducible delivery files. It is a delivery/runtime subsystem, not a design-layout subsystem.

## Ownership boundaries

Export Engine owns:

- exact-version export request/job state;
- server render/package orchestration;
- format validation;
- checksums and retention reuse;
- export manifest;
- final Artifact lineage;
- download authorization/signing boundary.

It does not own:

- design mutations or layout adaptation;
- Canvas editor state;
- model generation;
- video generation/composition;
- Brand/Identity rule definition;
- permanent storage credentials.

## Exact-version rule

Every request carries both:

```text
artifact_version_id
design_document_version_id
```

`ArtifactEngineExportSource` verifies the ArtifactVersion actually points at the requested DesignVersion. It loads that exact Design IR and executes NODE-41 `CanvasCompiler.fullCompile(document, false)`.

The resulting source snapshot pins:

```text
content_hash
constraint_snapshot_hash
compiler_version
compiler_compile_hash
resource_versions
font_versions
exact sanitized Design IR
durable render plan
rights/model/provenance refs
```

Once `start()` persists the snapshot, `execute()` never asks for project latest.

## Ephemeral URL rule

Compiler and Design IR resources may contain short-lived URI values used while resolving assets. Export does not persist or package them.

The source adapter strips keys ending in `_uri`, `_url`, `uri` or `url` before constructing the durable source snapshot. `exportFingerprint()` independently rejects any remaining ephemeral URI field.

LUMI Package therefore carries versioned asset identities, not presigned provider/storage URLs.

## Job state machine

```text
PENDING
  -> RENDERING
  -> PACKAGING
  -> VALIDATING
  -> READY

any active state -> FAILED
READY/FAILED -> EXPIRED by retention lifecycle
```

`start()` is idempotent by semantic fingerprint. `execute()` treats READY/FAILED/EXPIRED as terminal.

## Fingerprint

Fingerprint input includes:

- Export Engine semantic version;
- source ArtifactVersion/DesignVersion;
- source content/constraint hashes;
- NODE-41 compiler provenance;
- semantic variant specs.

It excludes request transport identity such as `requested_by`/new operation aliases so semantically identical READY output may be reused during retention.

## Rendering pipeline

```text
exact source snapshot
  -> SafeSvgRenderPlanSerializer
  -> SVG page(s)
  -> SVG direct
     or Chromium PNG/JPEG/WebP
     or JPEG page(s) -> PDF writer
  -> object store put
  -> checksum verify
  -> manifest/package
  -> readback verify
  -> Artifact Engine
```

### Safe SVG

The serializer consumes exact Design IR for geometry that is not carried by the runtime render plan, especially VECTOR_PATH.

Supported node types:

- FRAME;
- SHAPE;
- MASK;
- TEXT;
- IMAGE;
- VECTOR_PATH.

Container-only nodes are skipped because their children already carry world transforms.

VIDEO nodes fail and belong to NODE-48.

### Matrix

NODE-40/41 Matrix2D shape is:

```text
{ a, b, c, d, tx, ty }
```

Export does not use CSS-style `{e,f}` aliases.

### Images

Image resources are resolved by `(organization, project, asset_id, version)` and must become trusted inline `data:image/png|jpeg|webp;base64` values.

HTTP(S) href and nested SVG data images are rejected in V1.

### Fonts

Authorized font CSS may be embedded by the resource resolver. CSS with external `@import`/URL is rejected. When no export font is available, text explicitly falls back to `sans-serif`.

A later font-to-path capability must separately check rights; V1 does not claim automatic font outlining.

## SCALE/CROP and units

Export geometry is deliberately narrow:

- SCALE -> `xMidYMid meet`;
- CROP -> `xMidYMid slice` and requires target width+height.

Units:

```text
PX -> pixel target
IN -> value * DPI
MM -> value / 25.4 * DPI
```

Target raster dimensions are capped at 32768 px per side in V1.

`DESIGN_ADAPTATION` is not an Export operation. Create a new DesignVersion first.

## Raster worker

SDK transport:

```text
WorkerBackedRasterCodec
RasterWorkerTransport
```

Concrete pinned worker:

```text
scripts/export-raster-worker.mjs
@playwright/test 1.61.1 / Chromium
```

Worker security:

- rejects SVG script/external href;
- blocks HTTP(S) routes;
- decodes source SVG in browser;
- draws to Canvas;
- native `toBlob()` encodes PNG/JPEG/WebP;
- JPEG gets explicit white background;
- encoded blob is decoded again;
- decoded natural dimensions must equal request;
- returned MIME must equal requested format.

This prevents “rename bytes to .webp” style fake export support.

## PDF

`writeRasterPdf()` produces PDF 1.7 with one JPEG XObject per Frame/page.

Page size:

```text
points = pixels * 72 / dpi
```

`inspectRasterPdf()` independently checks header, xref, startxref, EOF, page count and MediaBox dimensions before output is accepted.

## Color and print honesty

V1 verified color target is SRGB.

Fail closed:

```text
DISPLAY_P3 -> not verified
CMYK       -> no real color management
PSD        -> unsupported
bleed/crop marks -> not implemented V1
```

UI/API must expose these as unsupported, not silently downgrade.

## ZIP writer

ZIP is store-mode and dependency-free. Validation includes:

- UTF-8 paths;
- path traversal/absolute/drive rejection;
- duplicate rejection;
- CRC32 payload validation;
- local size validation;
- central/local name, CRC, size and offset equality;
- EOCD count, offset and size;
- no trailing bytes;
- no multidisk.

`readStoreZipEntries()` is used by package validation/tests to verify package contents.

## LUMI package

V1 envelope:

```text
lumi/manifest.json
lumi/design-document.json
lumi/compiler-provenance.json
lumi/rights-summary.json
lumi/project-snapshot.json (optional)
lumi/exports/*
```

The package intentionally contains a sanitized semantic Design IR snapshot. It does not carry runtime URLs or provider secrets.

## Manifest

Manifest identity is canonical SHA-256 over all manifest fields except `manifest_sha256` itself.

Security scanner rejects key names representing:

- api keys/secrets;
- authorization/access/refresh/provider tokens;
- hidden prompts;
- system prompts.

Files include filename, MIME, checksum, size and available dimensions/page count.

## Object storage

Export Engine stores only stable object keys and checksums.

For every output:

1. worker returns bytes;
2. object store writes bytes;
3. returned checksum/size must match local bytes;
4. before READY, object is read back and checksum verified again.

No signed URL is persisted.

## Artifact integration

`ArtifactEngineExportAdapter` creates one Artifact per output file/manifest. This avoids ArtifactFile role conflicts for a multi-size export.

Each output gets:

- DRAFT ArtifactVersion;
- verified ArtifactFile;
- compiler provenance;
- source ArtifactVersion in provenance;
- `EXPORTED_FROM` edge;
- READY transition.

Source content/constraint hashes are rechecked before attaching output.

## API

Typed facade:

```text
createExport(spec)
runExport(org, export_job_id)
getExport(org, export_job_id)
getDownload(org, actor, job, file)
```

Status API never exposes storage keys or secrets.

## Downloads

`ExportDownloadService` conditions:

1. org-scoped job exists;
2. job is READY;
3. retention not expired;
4. file belongs to job;
5. authorization returns true;
6. TTL is 30..900 seconds;
7. signer creates fresh URL.

Server signer maps to NODE-19 S3 signed download support. Re-download creates a new URL but does not render again.

## Persistence

Migration: `0008_export_engine.sql`.

`export_jobs` stores exact source snapshot/spec/status/fingerprint. `export_files` stores durable key/checksum. `export_format_validations` records validation evidence. `export_download_audit` records authorization outcome/TTL only.

There is no signed URL column.

## Observability events

Reference runtime emits:

```text
export.created
export.rendering
export.variant_ready
export.ready
export.failed
```

Recommended production metrics:

- export queue wait;
- render time by format/dimensions;
- package time/files/bytes;
- validation failures by code;
- output bytes;
- READY reuse hit ratio;
- download denied rate;
- retention expiry count;
- Chromium worker failure rate.

## Validation

Static:

```text
python scripts/validate_export_engine.py
```

Type/tests:

```text
pnpm --filter @lumi/artifact-sdk typecheck
pnpm --filter @lumi/artifact-sdk test
```

Real raster smoke:

```text
pnpm exec playwright install --with-deps chromium
node scripts/export-raster-worker.test.mjs
```

DB:

```text
0001_artifact_engine.sql
0008_export_engine.sql
```

## Benchmark honesty

`export-benchmark.test.ts` measures deterministic 100-file store-mode ZIP packaging and validation. It is not a claim about production object storage, queue latency or Chromium high-resolution render SLO.

Those SLOs require hosted environment evidence.

## Completion policy

Implementation is not completion. NODE-49 stays **IMPLEMENTED / VALIDATING / not COMPLETE** until hosted contract/type/test/format/DB/benchmark jobs actually execute green.
