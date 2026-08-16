# Asset Storage V1 — Persistence Mapping

## Existing tables extended by `20260816_0004`

### `assets`

Adds `original_filename`, `declared_mime_type`, `media_kind`, `rejected_reason`, `created_by` and expands status to the NODE-18 lifecycle. Historical `failed` rows migrate to `rejected`.

The pre-existing `mime_type` column remains the canonical type field for READY assets. Runtime persistence must not treat a pre-validation placeholder as verified content type.

### `asset_files`

Adds role, MIME, duration, numeric fps, codec, color profile, alpha, metadata JSON and `verified_at`. `fps` is `NUMERIC(12,6)`; persistence does not introduce floating-point database truth.

Roles are `original`, `sanitized`, `thumbnail`, `medium`, `poster`.

### `asset_previews`

Adds source-file identity and preview media metadata. Preview rows point at derived object keys; they are not signed/public URLs.

### `asset_rights`

Adds `assertion`, `asserted_by`, `asserted_at`. `USER_OWNED` or `LICENSED` is only a user/source assertion. It does not force `commercial_use=true`.

A future SQL `AssetRepository` must write the rights row atomically with Asset + UploadSession creation. The contract already carries `rights_assertion` and `rights_source_uri`; the production adapter is tracked as a visible gap rather than silently omitted.

## New table: `asset_upload_sessions`

Stores only server-side upload control metadata: tenant/project/asset/file identities, canonical bucket/key, sanitized display filename, declared MIME, expected size/SHA-256, upload mode/state, storage multipart ID and expiry timestamps.

It never stores cloud access keys, signed upload URLs or signed query strings.

RLS scopes rows by `organization_id`. A security-definer trigger checks:

- Asset organization equals session organization;
- Asset project equals session project;
- Project belongs to the same organization;
- original object key exactly matches the canonical tenant prefix.

The application may SELECT/INSERT/UPDATE sessions but not DELETE them; lifecycle cleanup changes status and separately asks ObjectStore to remove an orphan candidate.

## New table: `asset_validation_reports`

Append-only evidence containing expected/actual checksum and size, sniffed MIME/media kind, scan result, acceptance decision, reason codes and safe metadata.

RLS scopes by tenant. The same-tenant trigger verifies Asset + UploadSession identities. The app role gets SELECT/INSERT only; UPDATE/DELETE is revoked.

## Object storage boundary

Database rows store stable `bucket` and `object_key`. They do not persist presigned URLs. Binary objects remain in the private `lumi-assets` bucket (or the configured S3-compatible equivalent).

## Migration rollback

`0004 -> 0003` removes the two new tables and NODE-18 columns/constraints. Lifecycle states that do not exist in NODE-17 map conservatively:

- `rejected -> failed`
- `uploading|verifying|scanning -> pending`

This rollback is for schema compatibility, not a promise that externally stored object bytes are deleted. Object retention/GC remains explicit.
