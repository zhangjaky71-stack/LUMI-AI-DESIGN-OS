# NODE-59 — Version History, Compare & Branch UX

> Phase: 7 Frontend Product  
> Status: **IMPLEMENTED / VALIDATING / NOT COMPLETE**  
> Priority: P0  
> Depends on: NODE-42 Artifact Engine, NODE-55 Infinite Canvas  
> Produces: immutable Version timeline, exact compare, fork, restore, safe provenance, approval/quality visibility

---

## 1. Product goal

NODE-59 turns NODE-42's immutable Artifact history into a user-facing product experience. It is deliberately different from Canvas undo/redo:

```text
Canvas undo/redo
= short-lived editing command history

ArtifactVersion history
= durable, immutable product history
```

The user can explore AI edits, compare outcomes, fork a direction and restore a historical result without losing later work.

---

## 2. Canonical ownership

NODE-59 does not create a second version engine.

```text
Version UI
  ↓ typed gateway
NODE-42 Artifact Engine
  ├─ Artifact
  ├─ ArtifactVersion
  ├─ ArtifactBranch
  ├─ ArtifactLineageEdge
  └─ ArtifactProvenance
```

The deterministic adapter imports `@lumi/artifact-sdk` and instantiates its real `ArtifactEngine` so append-only version, branch uniqueness, lineage-cycle protection and immutable provenance rules are exercised by the UI fixture.

No browser `localStorage`, `sessionStorage` or IndexedDB is canonical version truth.

---

## 3. Route and navigation

Primary route:

```text
/app/projects/{projectId}/versions
```

The Project detail surface exposes a `Versions` entry. The page links back to AI Workspace and Project Brief.

A Project may contain multiple versioned Artifacts. P0 supports at least:

- `DESIGN_DOCUMENT`;
- `RASTER_IMAGE`.

Artifact identity never changes merely because the user switches history views.

---

## 4. Version timeline

Each timeline item shows:

- exact version number/id;
- preview;
- creation time;
- creator type (`USER | AGENT | SYSTEM`) and creator id;
- branch;
- safe semantic change summary;
- `DRAFT / READY / APPROVED / REJECTED / ARCHIVED` status;
- quality score/label;
- branch HEAD marker;
- actions for Before, After, Restore and Provenance.

Branch history is rendered by following immutable parent links from the selected branch head. A fork may therefore reuse a historical source version without copying it into a fake branch-specific version.

---

## 5. Semantic change contract

For structured Design IR versions, semantic changes carry stable data:

```text
kind
node_id
node_name
property
before
after
protected_identity
```

Examples:

```text
Headline · font_size: 68 → 58
Feed / 4:5 · fill: #F3EBDD → #1C1917
Offer Badge · x: 920 → 944
Hero Product · asset_id unchanged · protected identity
```

The semantic summary is derived from structured change data. It is not an unrestricted LLM-generated description and is not treated as version truth by itself.

---

## 6. Exact compare

Every compare request names:

```text
artifact_id
from_version_id
to_version_id
```

The result returns `exact: true` and echoes the exact version identities.

### 6.1 Design IR compare

Implemented views:

- side-by-side;
- overlay;
- structured changed-node/property table.

### 6.2 Raster compare

Implemented views:

- side-by-side;
- overlay;
- wipe slider.

A heatmap remains an optional P1 visualization and is not required for NODE-59 completion.

---

## 7. Restore semantics

Restore is append-only and uses NODE-42's `ArtifactEngine.restore()` contract.

Example:

```text
main: v1 → v2 APPROVED → v3 → v4 HEAD
restore source = v2
```

Result:

```text
main: v1 → v2 APPROVED → v3 → v4 → v5 DRAFT HEAD
                                      ↑
                          content restored from v2

DERIVED_FROM(v2, v5)
metadata.operation = RESTORE
```

Required invariants:

- v2 remains APPROVED;
- v3 and v4 remain queryable;
- v5 has a new monotonically increasing version number;
- v5 is DRAFT;
- current branch head is v5;
- restore lineage points from exact source v2 to v5;
- historical content identity is not mutated.

The UI explicitly tells the user that Restore creates a new DRAFT version and does not delete later history.

---

## 8. Restore concurrency / CAS

Restore carries:

```text
expected_head_version_id
```

The deterministic runtime checks:

```text
branch.head_version_id === expected_head_version_id
```

**before** calling `ArtifactEngine.restore()`.

If another collaborator already created a new head, Restore fails closed with:

```text
BRANCH_HEAD_CONFLICT
```

No restore version is appended on that failed request.

Production must preserve this same compare-and-swap boundary transactionally.

---

## 9. Fork semantics

Forking an exact version creates an `ArtifactBranch`:

```text
source = v3
name = dark-direction

branch.base_version_id = v3
branch.head_version_id = v3
```

The source ArtifactVersion is reused; Fork does not duplicate immutable version content. P0 intentionally does not provide a complex merge UI.

Branch names are normalized and bounded before mutation.

---

## 10. Approval immutability

An APPROVED historical version is visually distinguished and remains immutable.

Any subsequent operation creates another version:

```text
v2 APPROVED
→ user/agent edit
→ v3 DRAFT

or

v2 APPROVED
→ Restore v2 while head=v4
→ v5 DRAFT
```

Approval does not turn history into a mutable document pointer.

---

## 11. Safe Provenance panel

NODE-59 exposes a permission-aware safe projection containing only user-relevant traceability:

- creator type/id;
- Agent Run / Task / Generation ids;
- model/provider identities;
- recipe/skill versions;
- exact source Asset ids;
- exact source ArtifactVersion ids;
- BrandRuleSet version;
- approval/quality checks;
- prompt hash;
- prompt-template version;
- constraint snapshot hash;
- Git SHA;
- compiler/document/compile identities.

The safe projection intentionally excludes:

```text
raw prompt text
system prompt
chain-of-thought
raw tool args/results
stack traces
secrets
signed storage URLs
```

The HTTP boundary is:

```text
GET /artifact-versions/{versionId}/provenance:safe
```

If authorization fails, UI surfaces restricted access and does not substitute hidden data.

---

## 12. Concurrent new head UX

When the user is reviewing:

```text
Before = v2
After  = v4
```

and a collaborator creates v5:

- v5 is added to timeline;
- UI shows an update notice;
- compare remains exactly v2 versus v4;
- the app does not silently jump After to v5.

This separates “new data is available” from “change the user's current review target.”

---

## 13. Production HTTP adapter

Typed endpoints:

```text
GET  /projects/{projectId}/versions?artifact_id={artifactId}
GET  /artifacts/{artifactId}/versions/compare?from={fromVersionId}&to={toVersionId}
POST /artifact-branches/{branchId}/restore
POST /artifacts/{artifactId}/branches
GET  /artifact-versions/{versionId}/provenance:safe
GET  /projects/{projectId}/versions?artifact_id={artifactId}&check_updates=1
```

The frontend never treats the deterministic in-memory engine as production persistence.

---

## 14. Deterministic E2E mode

Enabled only when:

```text
NODE_ENV != production
LUMI_VERSIONS_E2E=1
```

Fixture includes:

- Design Document v1-v4;
- Raster v1-v3;
- APPROVED v2 histories;
- USER and AGENT creators;
- BrandRuleSet and identity references;
- structured semantic changes;
- model/provider/run/task provenance;
- concurrent new-head injection;
- provenance-permission-denied Project.

Production build runs with this flag disabled and scans client chunks for fixture leakage.

---

## 15. Tests

### Unit

- branch normalization/validation;
- safe provenance allowlist;
- Restore creates new DRAFT;
- Restore preserves old APPROVED and later versions;
- Restore creates DERIVED_FROM lineage;
- stale head fails with `BRANCH_HEAD_CONFLICT` before restore mutation;
- Fork exact version;
- compare exact identities;
- concurrent head preserves historical compare availability;
- Raster identity/compare;
- Provenance authorization.

### Browser

- timeline/status/head rendering;
- Design IR semantic compare;
- Restore v2 → DRAFT v5 while v2/v4 remain;
- exact historical Fork;
- concurrent v5 notice with v2/v4 compare unchanged;
- Raster Wipe;
- safe provenance panel;
- provenance denied state;
- mobile layout.

NODE-58 through NODE-54 browser suites remain regression dependencies because Versions shares Project, Brand, Workspace and Canvas product boundaries.

---

## 16. CI

Dedicated `.github/workflows/versions-ui.yml` defines:

```text
versions-contract
versions-quality
versions-build
versions-browser-e2e
```

Contract gates run the frontend architecture-validator chain and typecheck Artifact SDK, Design IR, Canvas SDK and Web.

Quality gates run Artifact SDK tests, Versions units, relevant frontend regressions, lint and formatting.

Browser gates run NODE-59 and NODE-58/57/56/55/54 Playwright suites.

A GitHub account billing/spending failure before runner start is recorded as `BLOCKED BEFORE RUNNER`; it is neither PASS nor a code/test failure.

---

## 17. Production integration dependencies

NODE-59 UI/runtime contracts are implemented, but full production completion still requires:

- persistent NODE-42 Artifact/Version/Branch/Lineage APIs;
- transactional branch-head CAS;
- production semantic-diff generation;
- production Design/Raster preview projection;
- approval/quality joins;
- authorization-aware safe Provenance projection;
- concurrent head/event integration;
- tenant isolation/observability;
- hosted gates executing green.

---

## 18. Acceptance checklist

- [x] Project has a real Versions route.
- [x] Version timeline uses canonical ArtifactVersion identity.
- [x] Design IR semantic compare is implemented.
- [x] Raster side-by-side/overlay/wipe is implemented.
- [x] Restore appends a new DRAFT and preserves later history.
- [x] Restore uses expected-head CAS before mutation.
- [x] Fork creates a real ArtifactBranch from an exact source version.
- [x] APPROVED historical versions remain immutable.
- [x] Concurrent new head does not change compare targets.
- [x] Safe Provenance is permission-aware and excludes private execution data.
- [x] deterministic unit/browser/static gates are staged.
- [ ] hosted pinned gates have executed green.
- [ ] production NODE-42 services are connected.

---

## 19. Definition of Done

```text
version history E2E green
+ exact compare green
+ restore append-only/CAS green
+ fork green
+ provenance permission green
+ hosted pinned gates green
+ production NODE-42 integration green
```

Until hosted and production conditions are satisfied, status remains:

**IMPLEMENTED / VALIDATING / NOT COMPLETE**

下一节点：**NODE-60 — Export UI**。
