# LUMI Asset Storage V1

> Node: NODE-18  
> Contract: `lumi.asset-storage/1.0`  
> Status: IMPLEMENTED / VALIDATING

## 1. Purpose

Asset Storage is the binary boundary for uploaded and derived media. The API never proxies large upload bodies. A browser first obtains a short-lived signed request, uploads directly to S3-compatible storage, and then asks LUMI to complete the upload. Completion is not approval: the object must still pass streaming integrity, MIME, sanitizer, metadata and malware validation before the Asset becomes READY.

## 2. Storage boundary

Application code depends on `ObjectStore`, not on MinIO or AWS SDK types. V1 freezes these operations:

- `create_upload`
- `start_multipart`
- `sign_part`
- `complete_multipart`
- `abort_multipart`
- `head`
- `iter_bytes`
- `put_derived`
- `get_signed_download`
- `copy`
- `delete_candidate`

`MemoryObjectStore` is deterministic contract infrastructure. `S3CompatibleObjectStore` is a path-style AWS SigV4 adapter usable with local MinIO and compatible object stores.

## 3. Canonical object keys

Original upload keys are server-generated only:

```text
org/{organization_id}/project/{project_id}/asset/{asset_id}/original/{file_id}
```

Derived files replace `original` with the file role (`sanitized`, `thumbnail`, `medium`, `poster`). User filenames are sanitized metadata used only for display/download disposition. They never select a bucket or object key.

PostgreSQL validates original UploadSession keys again with a same-tenant trigger. RLS alone is not treated as sufficient protection against cross-tenant foreign-key relationships.

## 4. Upload lifecycle

```text
create-upload
  -> Asset UPLOADING + UploadSession PENDING
  -> direct signed PUT or multipart upload
  -> complete-upload
  -> object HEAD existence/size/checksum-if-available
  -> Asset VERIFYING + UploadSession VERIFYING
  -> validation worker streams the object
  -> checksum + actual size + magic-byte MIME + scanner + parser/sanitizer
  -> READY | REJECTED
```

The worker, not the API request handler, streams bytes to a temporary file. This keeps large binaries off the API memory path while still computing a trusted SHA-256 over the real object bytes.

A scanner-unavailable/error result fails closed when `QuotaPolicy.require_scanner=true`.

## 5. Integrity and content type

Client filename, extension and `Content-Type` are untrusted hints. Canonical MIME comes from file signatures/format parsing. V1 recognizes:

- PNG, JPEG, WebP
- SVG
- PDF
- MP4, QuickTime/MOV, WebM
- TTF, OTF, WOFF2

The upload declares expected byte size and SHA-256 before signing. Complete checks object existence and size and checks the storage-provided checksum when available. The validation worker always recomputes SHA-256 by streaming the stored bytes.

`assets.declared_mime_type` preserves the claim. Existing `assets.mime_type` is the canonical media field once the Asset is READY; non-READY rows must not be treated as verified MIME merely because a persistence adapter needs a placeholder value for the historical non-null column.

## 6. SVG security

Unsanitized SVG is never chosen for download/render when a sanitized file is available. V1 rejects active constructs including:

- scripts and `foreignObject`
- DOCTYPE/entity declarations
- `javascript:` URLs
- event-handler attributes
- non-fragment external `href`/`src`

Accepted SVG is serialized to a separate immutable `sanitized` AssetFile. The original remains provenance input but should not be rendered as trusted HTML.

## 7. Malware scanning

`FileScanner` is an adapter boundary. Implementations include:

- unavailable/fail-closed reference adapter
- local `clamscan` command adapter
- clamd TCP `INSTREAM` adapter

The local Compose `security` profile provides ClamAV. Production readiness must configure a real scanner; scanner absence is never silently upgraded to CLEAN.

## 8. Metadata extraction

`SafeMetadataExtractor` returns a bounded safe subset. Image dimensions/alpha are parsed where possible. Video metadata uses ffprobe for duration, resolution, fps and codec. Raw EXIF blobs and GPS are not exposed by the default contract.

Font V1 verifies recognized container signatures and records the container kind. Deep name-table/license parsing is an explicit follow-up gap, not inferred from a filename.

## 9. Preview pipeline

The preview adapter may emit:

- `thumbnail`
- `medium`
- `poster`

`FfmpegPreviewRenderer` is the production-oriented image/video adapter. `DeterministicPreviewRenderer` exists only to prove the pipeline contract without relying on an external binary during unit tests. Preview files are new derived objects with their own checksum and AssetFile identity; originals are immutable.

Queue-backed execution of preview work is intentionally deferred to NODE-19.

## 10. Signed downloads

A download is issued only after:

1. the caller authenticates;
2. the Asset resolves inside the selected organization;
3. the caller has project-read permission;
4. the Asset is READY;
5. a verified file exists.

The default TTL is 300 seconds and the hard adapter cap is 900 seconds. Signed query strings are ephemeral credentials and must not be copied into durable audit/log payloads. The object store bucket is private; public/CDN publishing is a later capability.

## 11. Quota

Before signing an upload LUMI checks:

- per-file maximum;
- current verified organization usage plus declared upload size;
- declared P0 media support.

The declared size is only a preflight reservation estimate. Durable usage/accounting must use the verified stored byte size.

## 12. Rights

User upload captures exactly one assertion:

```text
USER_OWNED | LICENSED | UNKNOWN
```

This assertion does not grant commercial rights. `commercial_use` remains an independent rights field and defaults false. A PostgreSQL repository must persist the Asset assertion/source/actor to `asset_rights` in the same transaction as the upload bundle.

## 13. Events

Frozen V1 event names:

```text
asset.upload.created
asset.upload.completed
asset.scan.failed
asset.ready
asset.rejected
asset.preview.created
```

Upload creation/completion and validation finalization also create audit entries through the repository transaction boundary.

## 14. Persistence

NODE-18 uses forward migration `20260816_0004` on NODE-17 `0003`. It adds `asset_upload_sessions`, `asset_validation_reports`, expands existing Asset/File/Preview/Rights metadata, enables RLS on new tenant tables, enforces canonical upload keys/same-tenant relations, and makes validation reports append-only for the application role.

No earlier migration snapshot is rewritten.

## 15. Completion boundary

Source implementation is not equivalent to production readiness. NODE-18 is not COMPLETE until the canonical Python 3.12 frozen environment actually executes unit/security tests, MinIO round trip, clamd test, PostgreSQL upgrade/invariants/downgrade/reapply, Ruff, Pyright and repository security gates.
