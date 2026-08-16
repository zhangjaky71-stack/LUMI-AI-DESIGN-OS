# NODE-15 Acceptance — Artifact / Version / Provenance V1

Status: **IMPLEMENTED / VALIDATING**

## Source completion

- [x] Frozen 9-type Artifact registry; `CANVAS` excluded as durable binary truth.
- [x] Frozen immutable ArtifactVersion content/provenance/rights/file contract.
- [x] Frozen DRAFT / READY / APPROVED / REJECTED / ARCHIVED lifecycle.
- [x] READY + required validation gate before APPROVED; APPROVED terminal.
- [x] Branch `base_version_id` / `head_version_id` semantics.
- [x] Fork points to source without rewriting the source version.
- [x] Restore creates a new version and a `DERIVED_FROM` edge; history is never rewound.
- [x] Seven frozen lineage edge types with same-tenant multi-parent DAG support.
- [x] Missing references, cross-tenant edges, duplicate edges and cycles fail closed.
- [x] Version SHA-256 content addressing and per-file SHA-256 checksum contract.
- [x] Six immutable file roles with object-key-only durable storage references.
- [x] Generated provenance requires provider/model/prompt hash and exact code Git SHA.
- [x] NODE-14 constraint snapshot can be bound to version/provenance and must match.
- [x] Append-only provenance annotation contract for corrections/review/operator notes.
- [x] Conservative tri-state Rights inheritance and Rights rejection approval block.
- [x] Secret-minimized transitive export provenance manifest + canonical manifest hash.
- [x] Logical archive / retention / legal-hold semantics.
- [x] Two-phase mark-and-sweep GC with positive delay and second live-reference check.
- [x] 20 deterministic lineage/rights/GC contract fixtures.
- [x] 9 deterministic machine-readable JSON Schema exports.
- [x] Architecture validator forbids ORM/provider/agent/queue/storage/image SDK coupling.
- [x] NODE-10 persistence baseline mapped without rewriting historical migrations.
- [x] Exactly 10 NODE-15-to-NODE-10 persistence gaps tracked in a machine-readable ledger.
- [x] Dedicated Python 3.12 / uv 0.11.28 frozen-install GitHub Actions gate.

## Persistence qualification

NODE-10 already contains the six intended Artifact persistence tables, but the schema predates the frozen NODE-15 contract. The unresolved fields/invariants are explicitly tracked in:

- `reports/nodes/NODE-15/persistence-gap-ledger.json`
- `docs/artifacts/PERSISTENCE-MAPPING-V1.md`

The original NODE-10 migration is not rewritten. A later forward migration must close the gaps and obtain PostgreSQL upgrade/invariant/downgrade/reapply evidence before Artifact runtime persistence can claim full NODE-15 compatibility.

Therefore:

```text
NODE-15 contract implemented != NODE-15 persistence runtime complete
```

## Executable validation required before COMPLETE

The dedicated workflow must execute, not merely be created. Required green evidence:

1. `uv sync --all-packages --frozen` on Python 3.12 / uv 0.11.28;
2. `NODE15_ARTIFACT_CONTRACT_VALIDATION_PASS`;
3. all `apps/api/tests/test_artifact_*.py` tests green;
4. exactly 9 schemas generated and parsed;
5. the 10-gap ledger parses and matches the validator;
6. Ruff green for Artifact source/tests/tools;
7. Pyright green for Artifact source/tests/tools;
8. repository CI/security gates green;
9. stacked NODE-09 through NODE-14 dependencies resolved in merge order.

No PostgreSQL runtime compatibility, object-storage deletion, provider generation, or production export behavior is claimed from this contract-only node.

## Merge rule

Do not mark NODE-15 COMPLETE or merge it to main out of dependency order. It is stacked on NODE-14 and must remain evidence-qualified until hosted gates can execute successfully.

Canonical contract: `docs/artifacts/ARTIFACT-VERSION-PROVENANCE-V1.md`  
Persistence mapping: `docs/artifacts/PERSISTENCE-MAPPING-V1.md`  
Next node after acceptance: **NODE-16 Authentication & Tenant**.
