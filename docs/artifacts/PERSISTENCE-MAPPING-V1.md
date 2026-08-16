# NODE-15 Persistence Mapping — NODE-10 Baseline

Status: **CONTRACT MAPPING / NOT A DATABASE PASS**

NODE-10 introduced the persistence baseline before NODE-15 froze the full Artifact/Version/Provenance semantics. This document prevents accidental equivalence between the existing ORM tables and the newer contract.

## Existing baseline tables

NODE-10 currently has:

- `artifacts`
- `artifact_branches`
- `artifact_versions`
- `artifact_edges`
- `artifact_files`
- `artifact_provenance`

Those tables remain useful and are the intended persistence home. NODE-15 does not create a parallel persistence store.

## Contract-to-baseline mapping

| NODE-15 contract | NODE-10 baseline | State |
|---|---|---|
| Artifact logical identity/type | `artifacts` | baseline exists |
| Artifact archive/retention/legal hold | soft-delete only | contract gap |
| Branch name/head | `artifact_branches` | baseline exists |
| Branch `base_version_id` | absent | contract gap |
| Version artifact/branch/version number | `artifact_versions` | baseline exists |
| Version direct `parent_version_id` | absent | contract gap |
| Version `content_hash` | nullable baseline column | contract requires non-null SHA-256 |
| Version `primary_file_id` | absent | contract gap |
| Version `design_document_version_id` | absent | contract gap |
| Version `constraint_snapshot_hash` | absent | contract gap |
| Version `ARCHIVED` status | baseline CHECK excludes it | contract gap |
| Multi-parent lineage | `artifact_edges` | baseline exists |
| Seven frozen edge types | baseline enum differs | contract gap |
| File object key/checksum/MIME/size | `artifact_files` | baseline exists |
| File role | absent | contract gap |
| File width/height/duration/metadata | absent | contract gap |
| Provenance JSON | `artifact_provenance.provenance_json` | baseline exists |
| Queryable model/task/generation/hash fields | JSON only | performance/indexing decision pending |
| Rights snapshot | absent on artifact/version | contract gap |

## Edge direction

NODE-15 defines:

```text
artifact_version_id = result
source_artifact_version_id = input/source
```

The current `artifact_edges.from_artifact_version_id` / `to_artifact_version_id` names are semantically ambiguous. The future persistence adapter must freeze one mapping and migration tests must verify it. Recommended mapping:

```text
from_artifact_version_id = result
 to_artifact_version_id = source
```

Renaming columns can be considered later, but runtime behavior must not reverse lineage.

## Required persistence follow-up

The machine-readable source of truth is `reports/nodes/NODE-15/persistence-gap-ledger.json`. Before production Artifact runtime writes can claim NODE-15 compatibility, a later migration must close all listed gaps with:

- tenant-safe foreign keys / same-organization guards;
- non-null cryptographic hash invariants;
- immutable approved content/provenance/file protection;
- branch/base/head same-artifact checks;
- lineage cycle prevention compatible with NODE-10 recursive guards;
- full frozen edge-type CHECK;
- rights snapshot persistence;
- file role/media metadata fields;
- restore/fork integration tests;
- upgrade/downgrade/reapply PostgreSQL evidence.

## Why NODE-15 does not edit the NODE-10 migration

The original NODE-10 migration is an immutable historical baseline and its hosted PostgreSQL workflow is currently blocked before runner allocation by the external GitHub Actions Billing/spending-limit condition. Rewriting that migration in place would destroy migration history and blur which schema was actually validated.

NODE-15 therefore freezes the target contract and explicit gap ledger. A new forward migration must be introduced by the runtime/persistence integration step; the old migration must not be silently rewritten.

## No false compatibility

Until the forward migration exists and executes green on PostgreSQL:

```text
NODE-15 contract implemented != NODE-15 persistence runtime complete
```

The contract tests, schemas and mapping validator are still valuable because they prevent future migration/application code from inventing a different artifact model.
