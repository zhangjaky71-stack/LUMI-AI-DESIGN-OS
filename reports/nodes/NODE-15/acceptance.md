# NODE-15 Acceptance Report — Artifact / Version / Provenance V1

> Status: **IMPLEMENTED / VALIDATING / BLOCKED_EXTERNAL**  
> Branch: `node-15-artifact-version-provenance`  
> Official node: **NODE-15 — Artifact / Version / Provenance Specification V1**  
> Base: `node-14-constraint-engine`

## 1. Delivered contracts

```text
contracts/artifacts/v1/
├── manifest.json
├── artifact-history.schema.json
├── provenance.schema.json
├── rights.schema.json
├── export-provenance-manifest.schema.json
└── fixtures/lineage.json
```

All schemas use JSON Schema Draft 2020-12.

## 2. Frozen artifact model

Artifact types: 9; CANVAS intentionally excluded.

Artifact, Branch, ArtifactVersion, LineageEdge and ArtifactFile are separate concepts. The reference runtime never models one mutable blob as the complete design history.

## 3. Version immutability

`ArtifactVersion` is a frozen record. Content identity includes content hash, schema, branch/parent, constraint snapshot, primary content refs, creator and creation time.

Content edits create new versions. Approval/status transition is controlled metadata and is asserted not to mutate content identity.

## 4. Status/approval gate

Reference status transitions are explicit. DRAFT cannot jump directly to APPROVED. READY -> APPROVED requires `required_validation_passed=True`.

This creates the contract boundary for NODE-14 postflight/approval evidence.

## 5. Branch / fork / restore

Implemented:

- branch name uniqueness per Artifact;
- branch head advancement on new version;
- fork branch from an existing version;
- restore creates a new version, never rewrites history;
- restore preserves selected content hash while using current constraint snapshot;
- restore records a DERIVED_FROM lineage edge to the selected historical version.

## 6. Lineage

Seven V1 edge types are frozen.

Reference graph supports multiple parents and cross-Artifact edges within a tenant. It rejects:

- self loops;
- duplicate relations;
- cycles;
- missing endpoints;
- cross-tenant lineage.

Fixture demonstrates restore and multi-parent lineage.

## 7. Content-address semantics

Files require SHA-256. DesignDocument content hash source is NODE-13 `LUMI_CANONICAL_JSON_V1`.

Content-hash dedupe lookup intentionally returns all matching versions; identical content does not collapse distinct history/provenance events.

## 8. File safety

ArtifactFile requires durable `storage_key`, checksum and byte size. URL-like storage keys containing `://` are rejected to prevent presigned URL persistence.

One file role per version is enforced by the reference history.

## 9. Provenance

Reference provenance tracks AgentRun, Task, Generation, Provider/Model, provider request, prompt hash/template, input assets/versions, Design IR schema, constraint snapshot, recipe, skills and code git SHA.

Provenance is immutable and only one record is accepted per ArtifactVersion in the V1 reference model.

Constraint snapshot hash must equal the version's recorded snapshot.

## 10. Rights model

Rights contract records source/license/usage permissions/attribution/source reference/review state.

Conservative inheritance is implemented:

```text
DENIED dominates UNKNOWN dominates ALLOWED
any attribution => attribution required
mixed license => UNKNOWN
RESTRICTED dominates review state
all VERIFIED => VERIFIED
```

Cross-tenant inheritance is rejected.

No generated artifact is automatically declared commercially safe.

## 11. Export provenance manifest

Secret-free manifest builder emits artifact version, created time, source IDs, model identity, rights summary, file checksums, constraint snapshot and code git SHA.

It does not emit raw prompt text, prompt hash, provider request ID, credentials or secret fields.

## 12. GC safety

Implemented mark-and-sweep reference contract:

1. current live storage keys prevent marking;
2. legal hold prevents marking/deletion;
3. active retention prevents marking/deletion;
4. unreferenced objects are marked first;
5. minimum delay is required before sweep;
6. current live refs are rechecked;
7. final confirmation is required immediately before delete.

A re-referenced marked object is not deletable.

## 13. Tests implemented

Reference unittest covers:

- frozen version content;
- branch head advancement;
- approval validation gate;
- fork;
- restore creates new history;
- multi-parent lineage;
- cycle rejection;
- cross-tenant lineage rejection;
- content-hash dedupe without history collapse;
- immutable provenance;
- constraint-snapshot consistency;
- conservative rights inheritance;
- GC live/retention/legal-hold safety;
- secret-free export manifest.

## 14. Contract validator

`scripts/validate_artifact_contracts.py` verifies:

- 9 artifact types and no CANVAS artifact type;
- frozen statuses and seven lineage types;
- SHA-256 / Design IR hash baselines;
- Draft 2020-12 schema IDs;
- version/edge enums match manifest;
- no presigned/secret/raw-prompt/password fields in public artifact contract;
- lineage fixture includes restore and multi-parent relationships;
- reference runtime import boundary remains infrastructure-free.

## 15. Independent CI gate

`.github/workflows/artifact-contract.yml` runs:

```text
Python 3.12 compileall
NODE-13 Design IR revalidation
NODE-14 Constraint revalidation
NODE-15 artifact/provenance contract validation
Artifact history stdlib unittest
```

It intentionally avoids the stale upstream `uv.lock`.

## 16. Current external blocker

GitHub hosted Actions still cannot start because account billing/payment or Actions spending requires attention. Previously retrieved GitHub annotation:

> The job was not started because recent account payments have failed or your spending limit needs to be increased. Please check the 'Billing & plans' section in your settings.

No hosted-runner PASS is claimed while jobs fail before checkout.

## 17. Acceptance checklist

- [x] Artifact / Version / Branch / Edge model frozen.
- [x] Version content identity immutable.
- [x] Fork semantics defined/executable.
- [x] Restore creates a new version.
- [x] multi-parent lineage supported.
- [x] cross-tenant/cycle lineage rejected.
- [x] provenance traces model/prompt hash/task/input/code.
- [x] files require checksum and durable key.
- [x] rights metadata contract published.
- [x] conservative rights inheritance implemented.
- [x] constraint snapshot tied to provenance.
- [x] export provenance manifest published.
- [x] GC mark/sweep safety implemented.
- [x] lineage fixture/tests committed.
- [x] independent CI gate committed.
- [ ] real Artifact Contract hosted-runner PASS.

## 18. Completion gate

After external Actions recovery:

1. real Python 3.12 runner starts;
2. compileall PASS;
3. upstream Design IR/Constraint validators PASS;
4. Artifact contract validator PASS;
5. Artifact history unittest PASS;
6. evidence recorded;
7. only then mark NODE-15 COMPLETE.

Completes Phase 1 contracts. Next official node: **NODE-16 — Authentication & Tenant**.
