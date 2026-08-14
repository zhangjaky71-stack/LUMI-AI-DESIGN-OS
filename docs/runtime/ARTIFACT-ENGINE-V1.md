# Artifact Engine V1

## Boundary

NODE-42 owns stable creative identity and immutable version history. It consumes NODE-41 `CompiledSceneSnapshot.render_plan` and `provenance`; it never reconstructs visual semantics from Pixi/browser state.

```text
Design IR -> Constraint -> Canvas Compiler
                    | render_plan + provenance
                    v
Artifact Engine -> Version / Branch / Lineage / Provenance / File / Export / GC
```

## Frozen entities

- `artifacts`: stable creative identity scoped by organization/project.
- `artifact_versions`: append-only content snapshots; `(organization_id, artifact_id, version_number)` unique.
- `artifact_branches`: mutable named heads; updates are compare-and-swap only.
- `artifact_edges`: lineage DAG; cross-tenant edges, self-loops and cycles are forbidden.
- `artifact_files`: immutable durable object metadata; runtime signed URLs are never stored as identity.
- `artifact_provenance`: one immutable record per version, including NODE-41 compiler identity.

## Version rules

Restore is append-only: restoring V1 while V4 is branch head creates V5 with V4 as parent and a lineage edge from V1 to V5. History is never rewound or overwritten.

Statuses: `DRAFT -> READY -> APPROVED`, with reject/archive side paths. Approval requires required validation. Content identity is not mutable through status transitions.

## Branch CAS

Repository implementations must update branch head using the equivalent of:

```sql
UPDATE artifact_branches
SET head_version_id = :next
WHERE organization_id = :org
  AND id = :branch
  AND head_version_id IS NOT DISTINCT FROM :expected;
```

Zero rows is a conflict. Blind overwrite is forbidden.

## File attach

`attachVerifiedFile` / `attach_verified_file` requires storage HEAD/stat to match storage key, checksum SHA-256, size and MIME (when reported) before DB/history attachment. Storage keys are durable object keys, never signed URLs.

## Compiler provenance

NODE-41 bridge records:

- compiler version
- document/schema/document version
- resource/style token versions
- font versions
- deterministic compile hash

Missing `compile_hash` fails closed for compiled Artifact provenance.

## Export

`ArtifactExportRegistry` is renderer-neutral. PNG/JPEG/PDF/SVG encoders are adapters. The Artifact Engine owns request/manifest/version/file semantics, not renderer internals. Export manifests include checksums and compiler provenance.

## GC

GC is mark -> delay -> recheck -> sweep. Branch heads/bases, READY/APPROVED versions, retention holds and legal holds are protected. Shared content-addressed objects are deleted only after the final reference disappears.

## Persistence

`db/migrations/0001_artifact_engine.sql` creates the six NODE-15 tables with tenant-aware composite FKs, version uniqueness, hash checks and CAS guidance.

## Completion gates

NODE-42 is COMPLETE only after hosted contract, TypeScript/Python quality, integration and benchmark gates execute green. A GitHub runner/account failure is an external blocker, not a code PASS or code failure.
