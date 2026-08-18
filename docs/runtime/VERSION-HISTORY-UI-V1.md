# Version History UI Runtime Contract V1

Status: NODE-59 core implementation contract.

## Canonical truth

The Versions UI is a projection over NODE-42 Artifact Engine. It does not own artifact history, branch heads, approvals, provenance, content hashes, or DesignDocument state.

- ArtifactVersion is immutable content history.
- ArtifactBranch owns a mutable head pointer guarded by compare-and-swap in Artifact Engine.
- Restore creates a new ArtifactVersion on a target branch. It never rewrites or deletes the source or later history.
- Fork creates a new ArtifactBranch rooted at an exact source version.
- Compare always uses two exact version IDs.
- Canvas opens an exact artifact version; background history refresh must never silently switch it.

## Product-safe read models

`GET /api/v1/artifacts/{artifact_id}/version-history` returns only:

- minimal artifact identity;
- branches and exact head/base IDs;
- version identity/status/hash/quality/creator/time;
- DesignDocument version reference;
- constraint snapshot hash;
- non-sensitive preview dimensions/mime metadata.

It intentionally omits ArtifactFile bucket/storage keys, full rights records, and full ProvenanceRecord.

`GET /api/v1/artifact-versions/{version_id}/provenance-safe` is an allowlisted projection containing model/provider identity, prompt hash/template version, source IDs, recipe/skill versions, code/constraint/compiler/agent versions and traceability completeness. It never returns raw prompt text, prompt refs, provider request IDs, messages, private reasoning, raw tool output, cookies, authorization headers or secrets.

The browser independently rejects private provenance-like keys before parsing the safe projection.

## User mutations

Browser product actions use dedicated user endpoints:

- `POST /artifact-versions/{version_id}/fork-user`
- `POST /artifact-versions/{version_id}/restore-user`

These requests cannot supply `created_by_type`, `created_by_id`, or canonical provenance. Creator identity comes from the authenticated request context.

For restore, the server derives a minimal provenance record referencing the exact source version and preserving only demonstrable source compiler/code/constraint identity. The target branch `expected_head_version_id` is mandatory as the client-known concurrency fence value (nullable only for an empty branch). A stale head returns conflict and the UI refreshes instead of retrying blindly.

## Structured compare

NODE-38 semantic diff is the only source for Design IR semantic summaries. The UI projects exactly these categories:

- `nodes_added`
- `nodes_removed`
- `properties_changed`
- `text_changed`
- `geometry_changed`
- `asset_replaced`
- `constraints_changed`

No LLM-authored change narrative is generated. Unknown diff metadata is not stringified into the UI.

Raster compare may display finite numeric metrics returned by Artifact Engine. A side-by-side/wipe/heatmap must not be simulated without a canonical preview renderer.

## Approval

ArtifactVersion status is the canonical approval badge. An APPROVED version remains immutable. New edits or restore operations produce a distinct version; they do not downgrade or mutate the old APPROVED record.

Full approval audit details are not yet part of the NODE-59 safe read projection and remain a P0 gap.

## Concurrency

The panel snapshots branch heads when an artifact/version is opened. Background refresh may update the timeline and show that a newer head exists, but must not change:

- the exact Canvas version currently viewed;
- either exact version ID in an active compare.

Opening the new head requires an explicit user action.

## Known P0 gaps

- canonical preview URLs/render service for visual side-by-side, raster wipe and heatmap;
- before/after property values beyond NODE-38 current semantic category output;
- approval audit projection/permissions;
- exact BrandRuleSet version in the safe version provenance projection;
- full branch breadcrumb/large-history pagination and virtualization;
- browser E2E and PostgreSQL integration proof;
- hosted GitHub Actions with executed green steps.
