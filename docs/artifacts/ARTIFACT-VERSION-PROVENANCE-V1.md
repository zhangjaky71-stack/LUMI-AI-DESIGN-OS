# LUMI Artifact / Version / Provenance Contract V1

Status: **FROZEN CONTRACT / NODE-15**  
Depends on: NODE-09 Domain Model, NODE-10 Persistence Baseline, NODE-13 Design IR V1, NODE-14 Constraint Engine V1

## 1. Durable truth

An `Artifact` is the logical work. An `ArtifactVersion` is an immutable content/provenance snapshot. Canvas is deliberately not an arbitrary binary artifact type: durable canvas truth remains `DesignDocument` / `DesignDocumentVersion` plus ArtifactVersion; viewport and transient renderer state are not provenance.

V1 artifact types are exactly:

- `DESIGN_DOCUMENT`
- `RASTER_IMAGE`
- `VECTOR_IMAGE`
- `VIDEO`
- `AUDIO`
- `PDF`
- `HTML`
- `ARCHIVE`
- `EXPORT_PACKAGE`

## 2. Version immutability

For an existing ArtifactVersion ID, these fields are immutable:

- organization/artifact/branch identity;
- parent version and version number;
- content hash;
- primary file and DesignDocumentVersion binding;
- quality score;
- NODE-14 constraint snapshot hash;
- creator and created-at identity;
- all file descriptors/checksums;
- provenance record;
- rights snapshot.

A status transition returns a new frozen model snapshot with the same version ID and unchanged content fields. New edits always create a new ArtifactVersion ID.

Allowed V1 lifecycle transitions:

```text
DRAFT -> READY | REJECTED | ARCHIVED
READY -> APPROVED | REJECTED | ARCHIVED
REJECTED -> ARCHIVED
APPROVED -> terminal
ARCHIVED -> terminal
```

Approval requires `READY`, a positive required-validation decision, and a non-rejected Rights review. An approved version cannot be edited or archived through the V1 version state machine.

## 3. Branch semantics

`ArtifactBranch` contains:

```text
id
organization_id
artifact_id
name
base_version_id?
head_version_id?
created_by_type
created_by_id?
created_at
```

Fork does not clone or mutate the source version. A new branch initially points `base_version_id` and `head_version_id` at the selected source. The first content change on that branch creates a new version.

Version numbers are branch-local positive integers. IDs and lineage, not a display ordinal, are the durable identity.

## 4. Restore semantics

Restore never rewinds or mutates history:

```text
select old source version
-> create new version on target branch
-> copy the selected immutable content reference/checksums
-> create current provenance for the restore operation
-> create DERIVED_FROM lineage edge to the selected source
-> advance target branch head
```

Restore provenance must explicitly list the restored source version in `input_artifact_version_ids`.

## 5. Lineage

Lineage edge direction is:

```text
artifact_version_id (result)
    -> source_artifact_version_id (input)
```

V1 edge types are exactly:

- `DERIVED_FROM`
- `EDITED_FROM`
- `GENERATED_FROM`
- `COMPOSED_FROM`
- `RESIZED_FROM`
- `EXPORTED_FROM`
- `REFERENCE_USED`

Multi-parent lineage is allowed, including composition of several source versions. Cross-artifact lineage is allowed only inside the same organization. Cross-tenant edges, missing references, duplicate edges and cycles fail closed.

The direct `parent_version_id` answers branch/edit ancestry for the same logical Artifact. General lineage answers all source relationships and can have many parents.

## 6. Content addressing

Every version has a lowercase hexadecimal SHA-256 `content_hash`. Every file has its own SHA-256 checksum. DesignDocument versions use NODE-13 canonical serialization hashing.

Content hashes support duplicate discovery, cache identity, provenance integrity and idempotent export. Duplicate content does not imply duplicate provenance; two versions may intentionally have the same content hash and different history.

## 7. Files

ArtifactVersion may contain immutable file descriptors with roles:

- `preview`
- `original`
- `thumbnail`
- `web-optimized`
- `print-pdf`
- `layer-data`

Each file freezes bucket/object key, MIME type, byte size, checksum, optional paired width/height, optional duration and bounded metadata. Durable records must never contain presigned/public HTTP URLs.

## 8. Provenance

`lumi.provenance/1.0` can answer:

```text
agent_run_id
task_id
generation_id
provider
model
provider_request_id
prompt_hash
prompt_ref
prompt_template_version
input_asset_ids
input_artifact_version_ids
design_ir_schema_version
constraint_snapshot_hash
recipe_version
skill_versions
code_git_sha
```

If `generation_id` exists, provider, model and prompt hash are mandatory. Sensitive prompt text is not part of the Artifact contract. `prompt_ref` is an access-controlled reference, not exported prompt content.

If both ArtifactVersion and Provenance carry a constraint snapshot hash, they must match exactly.

## 9. Rights / licensing

`lumi.rights/1.0` freezes the rights state used when a version is created or approved:

```text
source_type
owner_assertion
license_type
commercial_use
redistribution
training_use
attribution_required
source_reference
review_status
```

Boolean permissions are tri-state: `true`, `false`, or unknown. Rights inheritance is conservative:

- any explicit `false` wins;
- otherwise any unknown stays unknown;
- `true` only when every input is true;
- attribution is required if any source requires it;
- rejected source review makes inherited review rejected;
- different owners/licenses become `MIXED`.

LUMI does not infer legal ownership merely because a file exists in storage.

## 10. Export provenance manifest

Enterprise/export packages may include `lumi.export-provenance/1.0` with:

- root ArtifactVersion ID;
- transitive source ArtifactVersion IDs;
- source Asset IDs;
- provider/model pairs;
- rights snapshots;
- file checksums;
- code Git SHA;
- constraint snapshot hash.

The manifest intentionally excludes prompt text, provider request IDs, API keys, access tokens, signed URLs and other secrets.

## 11. Artifact archive and retention

Artifact deletion is logical archive first. Archive records a timezone-aware archive time and retention deadline. Legal hold remains independently enforceable and survives archival.

Object deletion is never an immediate post-transaction side effect.

## 12. GC mark-and-sweep safety

V1 GC contract is two-phase:

1. enumerate storage objects;
2. exclude all live DB references;
3. exclude retention references;
4. exclude legal-hold references;
5. mark the remaining objects with a positive delay;
6. after the delay, perform a second current-reference/retention/legal-hold check;
7. only then return deletion-safe candidates.

If an object becomes live again after mark, confirmation removes it from the deletion set.

## 13. API/runtime boundary

NODE-15 freezes contracts and pure deterministic behavior. Later API/runtime nodes own authorization, transactions and persistence adapters for:

```text
list versions
compare
fork
restore
approve/reject
get lineage
get provenance
archive
GC orchestration
```

The contract package must not import ORM, queue, LangGraph, provider, image-processing or storage SDKs.

## 14. Machine-readable schemas

`tools/node15/export_artifact_schemas.py` emits:

- `artifact-v1.schema.json`
- `artifact-branch-v1.schema.json`
- `artifact-version-v1.schema.json`
- `lineage-edge-v1.schema.json`
- `provenance-v1.schema.json`
- `rights-v1.schema.json`
- `export-provenance-manifest-v1.schema.json`
- `gc-candidate-v1.schema.json`

## 15. Persistence baseline mapping

NODE-10 already provides the six artifact persistence tables, but it predates the frozen NODE-15 contract. The exact deltas are machine-tracked in `reports/nodes/NODE-15/persistence-gap-ledger.json` and explained in `docs/artifacts/PERSISTENCE-MAPPING-V1.md`.

The gap ledger is not a waiver. Runtime writes must not claim full NODE-15 persistence compatibility until those gaps are migrated and PostgreSQL invariants are executed successfully.
