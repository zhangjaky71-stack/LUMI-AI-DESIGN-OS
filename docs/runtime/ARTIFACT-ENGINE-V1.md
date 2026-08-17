# LUMI Artifact Engine V1 — NODE-42

## Status

`IMPLEMENTED / VALIDATING`

NODE-42 turns the NODE-15 immutable artifact contracts into a transactional runtime. It is stacked on NODE-41 and uses NODE-38 semantic diff for Design IR comparisons.

## Runtime boundaries

```text
Artifact API
  -> ArtifactEngineService
     -> ArtifactRuntimeRepository
        -> PostgreSQL adapter / deterministic in-memory test twin
     -> ArtifactStoragePort
     -> DesignDocumentReader + NODE-38 SemanticDiff
     -> optional RasterVisualDiffPort
```

The canonical persisted domain objects remain NODE-15 `Artifact`, `ArtifactBranch`, `ArtifactVersion`, `ArtifactFile`, `LineageEdge`, `ProvenanceRecord`, and `RightsPolicy`.

## Immutable version semantics

An ArtifactVersion is append-only. Edits never update a historical version in place. `APPROVED` is terminal. A later edit creates a new `DRAFT` version.

Branch writes use optimistic head compare-and-swap. The PostgreSQL adapter locks the branch row with `SELECT ... FOR UPDATE`, verifies `expected_head_version_id`, allocates the next branch version number, inserts the immutable version/files/provenance/lineage, advances the head, and inserts the outbox event inside one database transaction.

## Artifact creation

Create supports two forms:

1. Artifact + `main` branch only.
2. Artifact + `main` + optional v1 as one transaction.

For the second form the branch is initially inserted with null head/base, v1 is inserted, then `base_version_id=head_version_id=v1` is committed in the same transaction. Partial creation is not allowed.

## Fork and restore

Fork creates a new branch whose base/head are the source immutable version.

Restore never rewinds a branch. It creates a new version whose content/file locations reuse the historical source where authorized. New `ArtifactFile` IDs are issued so immutable version ownership is explicit. The current head remains the parent and the restored source is represented by lineage.

## Lineage

NODE-42 persists the NODE-15 edge vocabulary:

- `DERIVED_FROM`
- `EDITED_FROM`
- `GENERATED_FROM`
- `COMPOSED_FROM`
- `RESIZED_FROM`
- `EXPORTED_FROM`
- `REFERENCE_USED`

Multi-parent lineage is supported. Cross-organization lineage is rejected before append.

## Provenance and traceability

Each version stores the full NODE-15 provenance JSON plus queryable columns for run/task/generation/provider/model/prompt/compiler/agent/constraint identities.

A deterministic completeness calculation records:

- `FULLY_TRACEABLE` or `PARTIAL`;
- completeness score;
- missing fields.

The runtime checks code Git SHA, compiler version, constraint snapshot, agent identity/version/recipe or skills when agent-created, and provider/model/prompt fields for generation-backed output.

Approval can be configured to require fully traceable provenance.

## File attachment and storage verification

Before an ArtifactFile can be attached, `ArtifactStoragePort.stat_object` must confirm the tenant-scoped object exists and its checksum, byte size, MIME type, and organization match the proposed file record.

Signed/public URLs are never persisted in ArtifactFile. Storage identity remains `{organization, bucket, storage_key, checksum}`.

The NODE-42 migration removes the old global `(bucket, object_key)` uniqueness constraint. A storage object may therefore be referenced by multiple immutable versions. The new uniqueness boundary is `(artifact_version_id, bucket, object_key)`. Authorization remains tenant scoped; equal hashes never grant cross-tenant access.

## Database migration

Revision `20260817_0011` follows `20260816_0010` and closes the major NODE-15 persistence shape gaps:

- artifact name/rights/lifecycle/legal-hold;
- branch base version + creator identity;
- version parent/primary file/design-document/constraint/rights/provenance completeness;
- `ARCHIVED` status;
- canonical lineage edge vocabulary;
- file role/dimensions/duration/metadata;
- queryable provenance columns/indexes;
- exact immutable version approval table;
- GC mark/audit tables;
- artifact transactional outbox.

Database status values remain lowercase for compatibility (`draft`, `ready`, `approved`, `rejected`, `archived`); repository mapping exposes canonical NODE-15 uppercase enums.

Downgrade explicitly refuses unsafe reversal if archived versions, `REFERENCE_USED` edges, or shared storage references exist.

## Compare

Design artifacts use a `DesignSemanticDiffPort`; `Node38SemanticDiffAdapter` delegates to the Python mirror of NODE-38 `compute_semantic_diff`.

Raster artifacts return primary-file metadata comparison and can add visual metrics through `RasterVisualDiffPort`. Generic artifacts fall back to immutable metadata/content-hash comparison.

## Transactional outbox

Artifact creation, version append, status transition, fork, and approval persist an `artifact_outbox_events` row in the same repository transaction as the domain mutation. Relay/delivery is intentionally a separate production adapter and is not claimed complete in NODE-42.

## Garbage collection

GC is two-phase:

```text
list storage objects
-> subtract protected DB references
-> MARKED + not_before
-> retention delay
-> recheck protected references
-> CANCELLED or storage delete
-> immutable GC audit
```

The production PostgreSQL repository is conservative: every existing ArtifactFile row protects its storage location. Purging version/file rows after retention/legal-hold evaluation is a separate scheduled lifecycle operation, preventing storage deletion underneath an immutable database reference.

## API

Required endpoints are installed under `/api/v1`:

- `GET /artifacts/{id}`
- `GET /artifacts/{id}/versions`
- `GET /artifact-versions/{id}`
- `GET /artifact-versions/{id}/lineage`
- `POST /artifact-versions/{id}/fork`
- `POST /artifact-versions/{id}/restore`
- `POST /artifact-versions/{id}/approve`
- `GET /artifact-versions/{a}/compare/{b}`

The runtime additionally exposes artifact creation, branch version creation, and READY transition. All routes are behind the existing v1 auth guard and use the existing `OrganizationId` header contract. A service factory can be installed in `app.state.artifact_engine_service_factory` to create an organization-scoped runtime.

## Local validation boundary

The deterministic in-memory runtime suite and Python syntax/static validators can be executed without infrastructure. The PostgreSQL adapter is compiled and statically checked, but a live PostgreSQL migration/concurrency run is not claimed until infrastructure executes it.

See `reports/nodes/NODE-42/gap-ledger.json` for open production integrations.
