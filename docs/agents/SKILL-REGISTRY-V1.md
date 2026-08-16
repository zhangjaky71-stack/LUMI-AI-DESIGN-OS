# Skill Registry V1 — NODE-31

## Purpose

NODE-31 is the canonical Skill publication and materialization layer for LUMI AI Design OS. It closes NODE-29's `SkillMaterializer` seam while keeping authoring/evaluation concerns outside the Deep Agent execution loop.

A Skill release is not only one prompt file. It is an immutable text package containing `SKILL.md`, optional supporting files, exact dependency refs, tool/permission requirements, deterministic hashes, evaluation evidence, and durable provenance.

## Core invariants

1. **Exact Skill versions are immutable.** Republishing identical runtime content is idempotent; different content under the same `skill_id@version` fails.
2. **Dependencies are exact-version only.** No mutable dependency alias is accepted in a published Skill manifest.
3. **Dependency hashes participate in Skill identity.** A Skill content hash covers its normalized package plus the exact content hashes of its direct dependencies.
4. **Evaluation evidence is content-bound.** The publish gate requires a passing result whose `subject_hash` equals the candidate runtime content hash.
5. **Runtime identity excludes mutable control metadata.** Publisher identity, timestamps, and evaluation timestamps do not alter the runtime content hash.
6. **Tenant visibility is hierarchical and fail-closed.** Project resolves project → organization → global only.
7. **Inherited exact versions cannot be shadowed.** A narrower scope must use a new version when overriding an inherited Skill.
8. **Materialization is exact and permission-aware.** The registry refuses Skills whose tools or sandbox/memory requirements are not granted by the resolved Agent plus invocation scope.
9. **Transitive dependencies never become extra NODE-29 Skill objects.** They are embedded below the requested Skill's `.lumi/dependencies/...` subtree.
10. **Registry storage and runtime staging are separate adapters.** Git-controlled publication does not require the Deep Agent process to own Git credentials.

## Publication contract

`SkillManifest` contains:

- `skill_id`
- exact `version`
- description
- UTF-8 text package files
- mandatory top-level `SKILL.md`
- exact dependency refs
- canonical Tool Gateway requirements
- required permissions (`sandbox.execute`, `memory.read:<scope>`, `memory.write:<scope>`)

Package paths are relative, traversal-free, and cannot claim the reserved `.lumi` namespace.

## Evaluation gate

`ThresholdSkillEvaluationGate` is the P0 publication gate. It validates:

- expected policy id;
- exact candidate `subject_hash`;
- `passed` status;
- minimum score.

The gate consumes durable `SkillEvaluationEvidence` with an external `evidence_ref`. It intentionally does not execute the benchmark suite itself. Benchmark/eval infrastructure produces the evidence; Skill Registry decides whether that evidence permits publication.

## Dependency DAG

Every dependency must already exist as an exact visible release. Self-dependency is rejected before lookup. Existing dependency trees are recursively checked for cycles/corruption.

Because exact releases cannot point to future unpublished dependencies, immutable publish ordering prevents ordinary DAG cycles by construction.

## Runtime materialization

`SkillRegistry.materialize(...)` directly implements NODE-29 `SkillMaterializer`.

For each requested exact ref it:

1. resolves the release in the invocation's project/org/global visibility chain;
2. verifies required tools against both Agent config and invocation grants;
3. verifies sandbox and memory requirements against both Agent config and invocation grants;
4. constructs the requested package;
5. embeds transitive dependencies under `.lumi/dependencies/<id>/<version>/...`;
6. writes `.lumi/dependencies.json` with dependency identities and hashes;
7. installs through `SkillPackageSink`;
8. returns exactly one `MaterializedSkill` for each requested ref.

The runtime path is fixed:

`/skills/<skill_id>/<exact_version>/SKILL.md`

No transitive dependency is returned as an additional `MaterializedSkill`, preserving NODE-29's exact requested-set invariant.

## Persistence adapters

### GitWorkspaceSkillRegistryStore

Stores canonical JSON releases under:

```text
<registry-root>/scopes/
  global/skills/<id>/versions/<version>.json
  organizations/<org>/shared/skills/<id>/versions/<version>.json
  organizations/<org>/projects/<project>/skills/<id>/versions/<version>.json
```

Writes use temp file + `fsync` + atomic replace. The adapter does not invoke `git`, perform network calls, or carry provider credentials.

### AtomicDirectorySkillPackageSink

Stages immutable package directories under a trusted host root using temp-directory construction and atomic rename. Existing directories are accepted only when their `.lumi/content-hash` marker matches the release hash.

Production sandbox/backend composition must map the staging root to the virtual `/skills` filesystem exposed by NODE-29/NODE-21.

## P0 acceptance

NODE-31 requires deterministic coverage for:

- exact-version immutability/idempotency;
- stale/failing/low-score eval rejection;
- dependency hash participation;
- cycle rejection;
- project/org/global isolation and inherited anti-shadow;
- exact NODE-29 materializer output;
- transitive dependency embedding without extra Skill objects;
- runtime tool/sandbox/memory permission denial;
- Git registry round-trip;
- atomic package staging.

## Next node

**NODE-32 — Context Compiler V1** should produce immutable project/brand constraint bundles for NODE-29 `PinnedContextBundle`, including source provenance, versioning, conflict policy, and prompt-injection-safe separation between hard constraints and dynamic task context.
