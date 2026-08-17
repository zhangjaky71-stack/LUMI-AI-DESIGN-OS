# EXPORT-ENGINE-V1

## Scope

NODE-49 turns one or more **approved exact ArtifactVersions** into downloadable files or a deterministic ZIP package. It is a delivery boundary, not a mutable document editor and not an Artifact version selector.

## Ownership boundaries

- **NODE-11** owns project/artifact export and package-download authorization.
- **NODE-19** owns durable worker scheduling, retries, cancellation and DLQ. NODE-49 uses `job_kind=export.package`.
- **NODE-42** owns immutable Artifact/ArtifactVersion truth and approval lifecycle.
- **Object storage** owns bytes. NODE-49 stores only internal bucket/key/checksum metadata.
- **NODE-49** owns exact-version capture, renderer/exporter selection, output verification, manifest/ZIP creation and short-lived download grants.

## Exact-version invariant

An export request must contain `artifact_version_id` for every item. Planning performs exactly:

```text
get_version(exact artifact_version_id)
→ get_artifact(version.artifact_id)
→ verify organization/project
→ require APPROVED
→ require rights not rejected
→ authorize export
→ persist immutable snapshot
```

NODE-49 never resolves branch head, latest version or latest approved version. The worker consumes only the persisted `ArtifactVersionSnapshot`; restart/retry does not re-select source content.

The snapshot captures:

- artifact id / exact version id / version number;
- artifact type and approval state;
- content hash;
- primary file id;
- every source file id, role, bucket, storage key, MIME, size and SHA-256;
- rights review state;
- capture timestamp.

## Export formats

P0 domain formats:

- `ORIGINAL`
- `PNG`
- `JPEG`
- `MP4`
- `PDF`
- `PPTX`

`ORIGINAL` always reads the captured exact source object and rechecks byte length and SHA-256 before publishing an export output.

`VerifiedSameFormatRenderer` supports real same-format delivery when the Artifact primary file already has the requested MIME. It does not rename bytes and pretend a conversion occurred. If MIME conversion is necessary, it fails with `EXPORT_TRANSCODER_REQUIRED`; production transcoders must implement `ExportRendererPort`.

## Long-running lifecycle

```text
PLANNED
→ exact snapshots + authorization
→ repository create / operation-id idempotency
→ NODE-19 export.package enqueue
→ QUEUED
→ worker execute
→ RENDERING
→ output size + checksum verification
→ PACKAGING
→ direct single-file package OR deterministic ZIP
→ READY
→ download authorization
→ short-lived grant
```

Terminal states are `READY`, `FAILED`, `CANCELLED`, `EXPIRED`. Cancelling a queued/in-flight job delegates to the linked NODE-19 runtime job.

## Idempotency

The export job id is deterministic from `(organization_id, operation_id)`. Repository uniqueness is `(organization_id, operation_id)` plus the full semantic hash. Reusing an operation id with changed exact versions, formats, names, TTL or limits fails closed.

The NODE-19 runtime job id is also deterministic from the export job id, preventing duplicate queue rows on replay.

## Batch and ZIP packaging

More than one output, or `force_zip=true`, creates a ZIP with:

- one entry per requested output;
- `manifest.json`;
- sanitized flat filenames only;
- duplicate-name rejection;
- maximum 500 entries;
- task-level byte ceiling;
- pre-package output SHA-256 verification;
- deterministic ZIP timestamps and permissions;
- whole-package SHA-256.

No archive extraction is performed by NODE-49.

## Manifest

`lumi.export-manifest/1.0` records:

- organization/project/export job/operation ids;
- exporter version;
- creation timestamp;
- every output filename, MIME, byte length and SHA-256;
- source artifact id and exact ArtifactVersion id;
- source file ids;
- renderer version.

The manifest contains no credentials, signed URLs, tokens or provider secrets.

## Authorization and download grants

NODE-11 authorization is required twice:

1. before an ArtifactVersion snapshot enters an export job;
2. every time a caller requests a download grant.

`download_ttl_seconds` is bounded to 60–3600 seconds. The signer returns a short-lived URL to the caller, while persistence records only:

```text
grant_id
export_job_id
package_id
organization_id
actor_id
issued_at
expires_at
```

There is deliberately no `url`, `token` or signature column.

## Persistence

Alembic `20260817_0018` follows NODE-48 `20260817_0017` and adds:

- `export_specs`
- `export_jobs`
- `export_items`
- `export_outputs`
- `export_download_grants`

`export_items.artifact_version_id` has a direct foreign key to NODE-42 `artifact_versions`, so the exact source version remains auditable after export completion.

## Runtime adapters

Implemented API adapters:

- `Node42ArtifactSnapshotAdapter`
- `Node19ExportQueueAdapter`
- `Node11ExportAuthorizationAdapter`
- `ShortLivedDownloadGrantAdapter`
- `PostgresExportRepository`
- restart-safe job/snapshot/package codec

Concrete object reader/writer, cloud presigner and format-conversion renderers remain environment-specific ports.

## Validation gates

The dedicated workflow defines:

1. compile + static architecture validator + gap-ledger parse;
2. exact-version / packaging / renderer / codec / NODE-42 adapter tests + Ruff + Pyright;
3. real PostgreSQL migration through Alembic head plus no-URL/token grant-schema assertions;
4. deterministic 500-item packaging benchmark.

Hosted execution and real object-storage/transcoder acceptance are required before NODE-49 can be marked COMPLETE.
