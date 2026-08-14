# NODE-42 — Artifact Engine Runtime

> Phase: 5 Design Intelligence  
> Status: **IMPLEMENTED / VALIDATING / not COMPLETE**  
> Priority: P0 / CORE  
> Depends on: NODE-15, NODE-18, NODE-38, NODE-41  
> Produces: Artifact / Version / Branch / Lineage / Provenance / File / Export / GC runtime

## Frozen boundary

All design outcomes are represented through stable `Artifact` identity and immutable `ArtifactVersion` history. NODE-42 consumes NODE-41 `CompiledSceneSnapshot.render_plan` and `provenance`; it does not reconstruct visual semantics from Pixi/browser state and does not introduce a second Design IR protocol.

## Implemented services

```text
ArtifactService
VersionService
BranchService
LineageService
ProvenanceService
ArtifactFileService
ExportService
GarbageCollectionService
```

Primary implementation evidence:

- `packages/artifact-sdk/src/types.ts`
- `packages/artifact-sdk/src/engine.ts`
- `packages/artifact-sdk/src/compiler-bridge.ts`
- `packages/artifact-sdk/src/hashing.ts`
- `packages/artifact-sdk/src/export.ts`
- `packages/artifact-sdk/src/gc.ts`
- `services/artifact-history/src/lumi_artifacts/history.py`
- `services/artifact-history/src/lumi_artifacts/runtime.py`
- `services/artifact-history/src/lumi_artifacts/storage.py`
- `db/migrations/0001_artifact_engine.sql`

## Version and branch semantics

Version creation is append-only. `(organization_id, artifact_id, version_number)` is unique. Branch heads use expected-head compare-and-swap; a stale expected head is a conflict and must never fall back to blind overwrite.

Restore never moves a historical pointer backward. Restoring an older version creates a new DRAFT version at the current branch tip and records lineage back to the restored source.

## Approval

`APPROVED` requires READY plus required validation evidence. Approval changes status/quality metadata only; the version content identity is immutable. Any subsequent edit creates a new DRAFT version.

## Provenance

Artifact provenance records exact refs and NODE-41 compiler identity:

```text
agent_run / task / generation
model / provider
prompt hash / template version
recipe / skill versions
input assets / artifact versions
constraint snapshot
git sha
compiler version
document/schema/document version
resource + style token versions
font versions
compile hash
```

`compilerProvenanceFromSnapshot()` accepts the actual NODE-41 `CompiledSceneSnapshot` type and fails closed when `compile_hash` is absent.

## File attach and storage

Files are attached only after storage HEAD/stat proves the durable object exists and checksum SHA-256, size and MIME match. `storage_key` is a durable object key, never a signed URL. Runtime presigned URLs are excluded from stable hashing.

## Export

`ArtifactExportRegistry` freezes renderer-neutral PNG/JPEG/PDF/SVG adapter contracts. NODE-42 owns export orchestration, manifest/provenance/file semantics and storage verification; actual encoder implementations remain replaceable renderer/export infrastructure and are not faked by this node.

## GC

GC follows mark → retention delay → graph/legal-hold recheck → delete. Branch heads/bases, READY/APPROVED versions, retention and legal holds remain live. Shared content-addressed blobs are removed only after the final reference disappears.

## Database

`db/migrations/0001_artifact_engine.sql` creates the NODE-15 frozen tables:

- `artifacts`
- `artifact_versions`
- `artifact_branches`
- `artifact_edges`
- `artifact_files`
- `artifact_provenance`

Organization-aware composite foreign keys, version/branch uniqueness, hash checks, durable storage-key checks and CAS guidance are encoded in the migration.

## Validation

Tests cover branch concurrency, restore, monotonic version numbers, approval gating, lineage safety, cross-tenant isolation, verified storage attachment, deterministic manifest identity, compiler provenance and GC live-ref protection. Existing NODE-15 Python lineage/rights/GC tests remain part of the regression suite.

Dedicated CI: `.github/workflows/artifact-engine.yml`.

NODE-42 becomes COMPLETE only when hosted `artifact-contract`, `artifact-quality`, `artifact-integration`, and `artifact-benchmark` execute green. External runner/billing failures are recorded as blockers, not PASS or code failures.

下一节点：NODE-43 Brand Rules Engine。
