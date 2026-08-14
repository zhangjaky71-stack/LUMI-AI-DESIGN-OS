# NODE-49 Acceptance — Export Engine

Status: **IMPLEMENTED / VALIDATING / not COMPLETE**

Base: `node-48-video-generation-release`

## Acceptance matrix

| Requirement | Evidence | Status |
|---|---|---|
| Exact ArtifactVersion | ExportSpec/source adapter/tests | Implemented |
| Exact DesignVersion | source adapter/real CanvasCompiler test | Implemented |
| No floating latest | `EXPORT_FLOATING_VERSION_FORBIDDEN` | Implemented |
| Pinned worker snapshot | `ExportSourceSnapshot` | Implemented |
| Compiler provenance | NODE-41 bridge/source adapter | Implemented |
| Ephemeral URI removal | source adapter + hashing guard | Implemented |
| PNG real encoder | Chromium worker | Implemented; hosted pending |
| JPEG real encoder | Chromium worker | Implemented; hosted pending |
| WebP real encoder | Chromium worker | Implemented; hosted pending |
| Real raster dimension decode | Chromium worker + smoke test | Implemented; hosted pending |
| HTTP(S) worker isolation | Playwright route abort | Implemented |
| Safe SVG | serializer/tests | Implemented |
| Actual Canvas tx/ty matrix | serializer/test | Implemented |
| Vector path exact geometry | Design IR `svg_path` fail-closed | Implemented |
| Image external href blocked | data raster URI policy | Implemented |
| Font fallback | `sans-serif` fallback test | Implemented |
| SCALE/CROP | meet/slice | Implemented |
| PX/MM/IN | DPI conversion | Implemented |
| PDF pages | deterministic writer | Implemented |
| PDF parser validation | xref/EOF/page count/MediaBox | Implemented |
| Batch ZIP | deterministic writer | Implemented |
| zip-slip defense | canonical safe paths | Implemented |
| ZIP CRC | payload CRC validation | Implemented |
| ZIP central/EOCD | structural validation | Implemented |
| LUMI Package | package content test | Implemented |
| Unicode filename | sanitizer/package tests | Implemented |
| Manifest SHA-256 | canonical manifest hash | Implemented |
| Sensitive metadata exclusion | recursive secret/prompt guard | Implemented |
| Storage checksum | write + readback verification | Implemented |
| Repeat export reuse | READY fingerprint test | Implemented |
| Re-download no rerender | authorization/sign test | Implemented |
| Signed URL authorization | ExportDownloadService | Implemented |
| Signed URL TTL | 30–900 seconds | Implemented |
| Signed URL not persisted | DB schema/static validator | Implemented |
| NODE-42 Artifact output | Artifact adapter/test | Implemented |
| EXPORTED_FROM lineage | Artifact adapter/test | Implemented |
| Artifact provenance | compiler/input source | Implemented |
| Export API facade | create/run/get/download | Implemented |
| PostgreSQL schema | `0008_export_engine.sql` | Implemented |
| Format validation table | migration | Implemented |
| Download audit table | migration | Implemented contract |
| 62-case conformance | fixture/static validator | Implemented synthetic evidence |
| 100-file benchmark | targeted benchmark test | Implemented; hosted pending |
| PSD | fail-closed | Implemented |
| CMYK | fail-closed | Implemented |
| Display P3 | fail-closed | Implemented |
| bleed/crop marks | fail-closed | Implemented V1 boundary |
| DESIGN_ADAPTATION in Export | explicitly forbidden | Implemented architecture boundary |

## Security assertions

1. Export accepts exact source version identities only.
2. Worker execution uses the pinned source snapshot, not project latest.
3. Runtime compiler URLs are stripped before durable persistence/package creation.
4. Server raster worker blocks HTTP(S) and rejects external SVG resources.
5. ZIP paths reject absolute, drive and traversal entries.
6. ZIP validates CRC/local/central/EOCD before READY.
7. No signed URL is stored in `export_jobs` or `export_files`.
8. Download signing happens only after authorization and uses bounded TTL.
9. Hidden/system prompts and common secret/token key names are excluded from export metadata.
10. CMYK/Display P3/PSD/print marks are not silently downgraded or falsely advertised.

## Artifact assertions

Each output/manifest is persisted as a verified NODE-42 ArtifactVersion with:

```text
source ArtifactVersion -> EXPORTED_FROM -> export ArtifactVersion
compiler provenance
constraint snapshot hash
manifest SHA reference
verified stable storage key/checksum
READY transition after validation
```

## Format evidence honesty

The Chromium worker and smoke test are implemented, but this acceptance report does not call PNG/JPEG/WebP validation PASS until hosted Chromium actually runs. PDF/SVG/ZIP implementation also remains hosted-validation pending.

## Local validation limitation

The available local environment does not match the repository toolchain and cannot provide exact dependency-complete evidence. Therefore local implementation review is not converted into PASS.

## Hosted validation requirement

Required jobs:

```text
export-contract
export-quality
export-formats
export-db
export-benchmark
```

A zero-step GitHub Actions account/billing failure must be recorded as an external blocker. It is neither PASS nor an observed code/test failure.

## Current decision

**IMPLEMENTED / VALIDATING / not COMPLETE**

Completion requires all hosted jobs above to execute green, including real Chromium PNG/JPEG/WebP smoke and PostgreSQL migration validation.
