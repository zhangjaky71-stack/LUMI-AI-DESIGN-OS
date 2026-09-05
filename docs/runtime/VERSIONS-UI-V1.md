# Versions UI Runtime V1

## Purpose

NODE-59 exposes immutable Artifact history to end users without creating a browser-side version database or confusing Canvas undo with durable ArtifactVersion history.

Canonical ownership stays in NODE-42:

```text
Artifact
├─ ArtifactBranch
├─ ArtifactVersion (append-only)
├─ ArtifactLineageEdge
└─ ArtifactProvenance
```

The frontend is a read/action projection over those identities.

## Route

```text
/app/projects/{projectId}/versions
```

The project detail page links to this route. The page can switch between multiple Artifacts in the same Project, including structured `DESIGN_DOCUMENT` and raster outputs.

## Production API boundary

```text
GET  /projects/{projectId}/versions?artifact_id={artifactId}
GET  /artifacts/{artifactId}/versions/compare?from={versionId}&to={versionId}
POST /artifact-branches/{branchId}/restore
POST /artifacts/{artifactId}/branches
GET  /artifact-versions/{versionId}/provenance:safe
GET  /projects/{projectId}/versions?artifact_id={artifactId}&check_updates=1
```

Restore carries `expected_head_version_id`; production must enforce compare-and-swap before mutation.

## Restore semantics

Restore is append-only:

```text
main: v1 → v2 APPROVED → v3 → v4 HEAD
restore source v2
→ new v5 DRAFT
→ parent = v4
→ DERIVED_FROM(v2, v5) with RESTORE lineage
```

The original v2 remains APPROVED and immutable. v3/v4 remain queryable. No historical pointer is moved backwards.

## Branch / Fork semantics

Fork selects an exact ArtifactVersion and creates a named `ArtifactBranch`:

```text
source v3
→ branch dark-direction
   base = v3
   head = v3
```

NODE-59 does not introduce P0 merge UI or copy content into a fake parallel Artifact.

## Compare semantics

Every compare request names two exact ArtifactVersion IDs.

For structured Design IR, UI renders:

- side-by-side previews;
- overlay;
- structured semantic property changes;
- changed node/property identities;
- protected identity markers.

For raster Artifacts, UI also provides a wipe slider. A later visual heatmap remains optional.

Semantic summaries are derived from structured operations/diffs in the runtime contract; an unrestricted LLM prose summary is not authoritative version truth.

## Concurrency

If a collaborator creates a newer head while the user is comparing v2 and v4:

```text
v5 appears
→ show update notice
→ keep compare From=v2 / To=v4
```

The UI never silently changes the exact pair being reviewed.

Restore uses the branch head observed by the user as `expected_head_version_id`. A changed head produces `BRANCH_HEAD_CONFLICT` before restore.

## Provenance safety

The UI consumes a safe allowlisted projection only:

- creator type/id;
- Agent Run / Task / Generation IDs;
- model/provider identity;
- recipe/skill versions;
- source Asset IDs;
- source ArtifactVersion IDs;
- BrandRuleSet version;
- quality/approval facts;
- prompt hash and prompt-template version;
- constraint hash;
- Git/Compiler identity.

It deliberately excludes:

```text
raw prompt text
system prompt
chain-of-thought
raw tool args/results
stack traces
secrets
signed URLs
```

Authorization is enforced at the provenance endpoint. The UI handles `PROVENANCE_FORBIDDEN` without substituting hidden data.

## Deterministic test mode

Enabled only when:

```text
NODE_ENV != production
LUMI_VERSIONS_E2E=1
```

The fixture contains:

- structured campaign Artifact v1-v4;
- raster Artifact v1-v3;
- APPROVED historical versions;
- semantic text/style/layout/identity changes;
- safe provenance;
- concurrent-head injection;
- permission-denied Project.

The deterministic gateway instantiates canonical `@lumi/artifact-sdk` `ArtifactEngine` and uses its append-only version, branch, lineage and immutable provenance rules rather than implementing a second mutation engine.

## Browser persistence

No `localStorage`, `sessionStorage` or IndexedDB is used as canonical version truth. Compare selection is ephemeral UI state only.

## Production completion boundary

NODE-59 remains integration-dependent until real NODE-42 services back the HTTP adapter with tenant authorization, durable version/branch/lineage/provenance storage, semantic diff generation, preview rendering, approval/quality projection and concurrency/CAS behavior.
