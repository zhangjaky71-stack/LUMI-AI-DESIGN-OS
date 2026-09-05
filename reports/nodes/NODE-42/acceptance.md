# NODE-42 — Artifact Engine Acceptance

> Status: **IMPLEMENTED / VALIDATING / not COMPLETE**  
> Branch: `node-42-artifact-engine`  
> Base: `node-41-canvas-compiler-release`

## Scope evidence

| Requirement | Evidence | State |
| --- | --- | --- |
| Artifact stable identity | `packages/artifact-sdk/src/types.ts` | IMPLEMENTED |
| Immutable versions | TS/Python runtime + DB unique version number | IMPLEMENTED |
| Branch expected-head CAS | `engine.ts`, Python `runtime.py`, migration CAS contract | IMPLEMENTED |
| Restore creates new version | TS `restore`, existing Python `restore_version` | IMPLEMENTED |
| Lineage DAG/cycle protection | TS/Python history | IMPLEMENTED |
| Organization isolation | runtime tenant checks + composite DB FKs | IMPLEMENTED |
| Immutable provenance | TS/Python + one-row DB PK | IMPLEMENTED |
| NODE-41 compiler provenance | `compiler-bridge.ts` | IMPLEMENTED |
| Compiler/resource/style/font versions | Artifact provenance contract | IMPLEMENTED |
| Deterministic stable manifest hash | `hashing.ts` | IMPLEMENTED |
| Signed URLs excluded from identity | manifest regression test | IMPLEMENTED |
| Verified storage attach | TS `attachVerifiedFile`, Python `storage.py` | IMPLEMENTED |
| HEAD/checksum/size/MIME fail-closed | TS/Python tests | IMPLEMENTED |
| Durable storage key, not URL | model + runtime + DB CHECK | IMPLEMENTED |
| PNG/JPEG/PDF/SVG export boundary | `ArtifactExportRegistry` | IMPLEMENTED adapter boundary |
| Export manifest | `buildArtifactExportManifest` + Python existing manifest | IMPLEMENTED |
| Reference-safe GC | TS `gc.ts` + Python existing two-pass GC | IMPLEMENTED |
| PostgreSQL schema | `db/migrations/0001_artifact_engine.sql` | IMPLEMENTED |
| Static architecture validator | `scripts/validate_artifact_engine.py` | IMPLEMENTED |
| Dedicated CI | `.github/workflows/artifact-engine.yml` | IMPLEMENTED; hosted execution pending |

## Non-negotiable invariants

1. Restore never rewrites history; it appends a new DRAFT version.
2. Version numbers are unique and monotonic per artifact.
3. Branch heads advance only by expected-head compare-and-swap.
4. APPROVED is reachable only from READY with required validation evidence.
5. Artifact files are attached only after storage object metadata matches checksum, size and MIME.
6. Signed/presigned URLs are runtime transport data and never stable identity inputs.
7. Lineage is tenant-local and acyclic.
8. Artifact compiler provenance is copied from NODE-41 `CompiledSceneSnapshot.provenance`; missing compile hash fails closed.
9. GC requires mark/delay/recheck and protects branch heads, approved/ready objects, retention and legal holds.

## Database acceptance

The first real migration under the previously empty `db/migrations` directory creates the NODE-15 frozen tables:

- `artifacts`
- `artifact_versions`
- `artifact_branches`
- `artifact_edges`
- `artifact_files`
- `artifact_provenance`

It uses organization-aware composite foreign keys, unique artifact version numbers, unique branch names, SHA-256 checks, durable storage key checks and the documented CAS update pattern.

## Compiler integration

`compilerProvenanceFromSnapshot()` accepts the real NODE-41 `CompiledSceneSnapshot` type and requires `compile_hash`. Artifact Engine therefore does not reconstruct provenance from Pixi/browser objects.

## Export boundary

NODE-42 freezes export orchestration and adapter contracts for PNG/JPEG/PDF/SVG. Actual raster/vector/PDF encoder implementations remain replaceable infrastructure; this node does not fake encoded files. A successful adapter payload must still pass storage verification before attachment to an ArtifactVersion.

## Test evidence present

- TS: CAS, version numbering, restore append-only, approval gate, storage verification, stable hash, GC reachability.
- Python: CAS, monotonic numbering, storage verification, compiler provenance normalization, plus existing NODE-15 history/lineage/rights/GC regression suite.
- Static validator: frozen table names, branch CAS contract, NODE-41 bridge and runtime files.

## Hosted completion gates

1. `artifact-contract` executes green.
2. `artifact-quality` executes TS and Python suites green.
3. `artifact-integration` executes NODE-41 bridge/conformance green.
4. `artifact-benchmark` executes green.
5. No NODE-38/39/40/41 frozen contract drift.

## Current disposition

Engineering scope is implemented and published to the development branch. NODE-42 intentionally remains **IMPLEMENTED / VALIDATING / not COMPLETE** until hosted jobs actually execute green. If the existing GitHub billing/spending-limit condition prevents jobs from starting, record it as an external CI blocker rather than code failure or PASS.
