# LUMI Artifact / Version / Provenance V1

> Status: **FROZEN FOR NODE-15 IMPLEMENTATION / VALIDATING**  
> Depends on: NODE-13 Design IR V1 + NODE-14 Constraint Engine V1

## 1. Ownership

```text
Artifact = logical work identity
ArtifactVersion = immutable content/provenance snapshot
Branch = named history pointer
LineageEdge = derivation/reference relation
ArtifactFile = durable checksum-addressed file reference
Provenance = how/why/by-whom the version was produced
Rights = what is known about permitted use
```

Canvas renderer state is not an Artifact binary type. The durable truth is DesignDocument/ArtifactVersion plus separately owned user view state.

## 2. Artifact types

V1 freezes:

```text
DESIGN_DOCUMENT
RASTER_IMAGE
VECTOR_IMAGE
VIDEO
AUDIO
PDF
HTML
ARCHIVE
EXPORT_PACKAGE
```

`CANVAS` is intentionally absent.

## 3. Version immutability

Version content identity includes artifact/branch/parent/schema/version number/content hash/constraint snapshot/file or DesignDocument reference/creator/time.

It is never edited in place. A content edit creates a new version.

Lifecycle status is separately controlled metadata. `DRAFT -> READY -> APPROVED` does not permit changing the frozen content identity. `APPROVED` requires evidence that required validation passed.

## 4. Status

```text
DRAFT -> READY | REJECTED | ARCHIVED
READY -> APPROVED | REJECTED | ARCHIVED
APPROVED -> ARCHIVED
REJECTED -> ARCHIVED
ARCHIVED terminal
```

Approval cannot jump directly from DRAFT and cannot occur without required validation.

## 5. Branch and restore

Fork creates a new branch pointer whose base/head initially reference an existing version.

Restore never rewinds history:

```text
current head v3
select old v1
-> create new v4 with v1 content
-> parent_version_id = v3
-> DERIVED_FROM edge v1 -> v4 with operation=RESTORE
-> branch head = v4
```

Thus chronology and content derivation are both visible.

## 6. Lineage

V1 edge types:

```text
DERIVED_FROM
EDITED_FROM
GENERATED_FROM
COMPOSED_FROM
RESIZED_FROM
EXPORTED_FROM
REFERENCE_USED
```

Multiple parents are allowed; for example product source + logo source + generated background may all point to one output version.

Lineage may cross Artifact identities inside one tenant. Cross-tenant lineage and cycles are rejected.

## 7. Content hash

Files use lowercase SHA-256 checksum. DesignDocument versions use NODE-13 `LUMI_CANONICAL_JSON_V1` content hash.

Identical content hashes support dedupe/cache, but do **not** collapse distinct version history. Two versions can intentionally reference identical content and still represent different restore/approval/provenance events.

## 8. Files

A version may own role-addressed files:

```text
PREVIEW
ORIGINAL
THUMBNAIL
WEB_OPTIMIZED
PRINT_PDF
LAYER_DATA
```

File contract stores durable object `storage_key`, MIME, byte size, checksum, optional dimensions/duration and metadata. `storage_key` is not a URL and long-lived presigned URLs are forbidden from this contract.

## 9. Provenance

Provenance can trace:

```text
AgentRun
Task
Generation
Provider / Model / provider request
prompt hash / template version
input Asset IDs
input ArtifactVersion IDs
Design IR schema version
Constraint snapshot hash
Recipe version
Skill versions
code git SHA
```

Raw prompt text/secrets do not belong in export provenance. Sensitive prompt storage, if needed, is separately access controlled.

The provenance constraint snapshot hash must equal the ArtifactVersion snapshot hash.

## 10. Constraint snapshot

NODE-14 produces deterministic constraint snapshot SHA-256. NODE-15 records it with the version and provenance, so later audit can answer what hard/soft rules applied when a result was produced or approved.

## 11. Rights

Rights is distinct from provenance.

It records:

```text
source type
owner assertion
license type
commercial use
redistribution
training use
attribution requirement
source reference
review status
```

LUMI never turns `GENERATED` into an automatic commercial-rights guarantee.

## 12. Conservative rights inheritance

When an ArtifactVersion derives from multiple inputs:

- any DENIED capability => output DENIED for that capability;
- otherwise any UNKNOWN => output UNKNOWN;
- only all ALLOWED => output ALLOWED;
- attribution is required if any source requires it;
- mixed license types => UNKNOWN;
- any RESTRICTED review => output RESTRICTED;
- only all VERIFIED => output VERIFIED.

Cross-tenant rights inheritance is rejected.

This is intentionally conservative; later legal/product policy may add explicit licensed transformations but cannot silently weaken source restrictions.

## 13. Export provenance manifest

Enterprise/export packages may emit a secret-free manifest containing:

```text
artifact version
created time
source IDs
provider/model identifiers
rights summaries
file checksums
constraint snapshot hash
code git SHA
```

It excludes secret keys, provider credentials and raw prompt text.

## 14. GC safety

Physical object deletion follows mark-and-sweep:

```text
collect current DB live file refs
-> exclude legal hold
-> exclude active retention window
-> mark unreferenced candidate
-> wait minimum delay
-> recompute live refs
-> final confirmation
-> physical delete
```

A re-referenced object after marking is not deleted. Database commit never immediately triggers destructive storage deletion.

## 15. Reference runtime

`services/artifact-history/src/lumi_artifacts` implements dependency-free reference semantics for:

```text
version immutability
status transitions
branch head
fork
restore
lineage DAG
cross-tenant rejection
content-hash lookup
provenance integrity
rights inheritance
GC safety
export provenance manifest
```

Production persistence in NODE-42 may optimize storage but must remain conformant.

## 16. Contract files

```text
contracts/artifacts/v1/
├── manifest.json
├── artifact-history.schema.json
├── provenance.schema.json
├── rights.schema.json
├── export-provenance-manifest.schema.json
└── fixtures/lineage.json
```

## 17. Validation

`.github/workflows/artifact-contract.yml` runs without the stale upstream uv lock:

```text
compile Phase-1 reference runtimes
revalidate NODE-13 Design IR
revalidate NODE-14 Constraint contract
validate NODE-15 schemas/fixtures/dependency boundary
run Artifact history stdlib tests
```

## 18. Explicit non-ownership

NODE-15 does not implement SQL persistence adapters, object-store deletion jobs, auth/RBAC, full visual validators, production Artifact Engine APIs or collaboration merge. Those later Nodes must implement adapters around this frozen history contract.
