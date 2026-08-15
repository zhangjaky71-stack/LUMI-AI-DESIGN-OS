# NODE-59 Acceptance Evidence

> Node: Version History, Compare & Branch UX  
> Status: **IMPLEMENTED / VALIDATING / NOT COMPLETE**  
> Base: `node-58-brand-kit-release` @ `be1e6e35335ae389b3eb63c13c604427f8b7b8fb`

## Product surface implemented

- `/app/projects/{projectId}/versions` product route.
- Project detail entry into Versions.
- Multi-Artifact history selector.
- Branch selector and immutable parent-chain timeline.
- Version preview, creator/time, status, quality and HEAD badges.
- Exact Before/After selectors.
- Design IR side-by-side/overlay semantic compare.
- Raster side-by-side/overlay/wipe compare.
- Append-only Restore UX.
- Exact historical Fork UX.
- Concurrent-head update notice without compare retargeting.
- Permission-aware safe Provenance panel.
- Responsive/mobile layout.

## Canonical ownership

NODE-59 imports `@lumi/artifact-sdk` and the deterministic adapter instantiates canonical `ArtifactEngine`.

Canonical durable identities remain:

```text
Artifact
ArtifactVersion
ArtifactBranch
ArtifactLineageEdge
ArtifactProvenance
```

Versions UI does not invent browser-local canonical version records.

## Restore safety

The deterministic runtime checks:

```text
branch.head_version_id === expected_head_version_id
```

before calling:

```text
ArtifactEngine.restore(...)
```

Successful restore:

```text
v1 → v2 APPROVED → v3 → v4 HEAD
restore v2
→ v5 DRAFT HEAD
→ DERIVED_FROM(v2, v5)
```

v2 remains APPROVED and v3/v4 remain queryable.

A stale head returns `BRANCH_HEAD_CONFLICT` without appending a restore version.

## Fork safety

Fork creates a real `ArtifactBranch` whose base/head both point to the exact historical source version. It does not duplicate immutable content and does not imply a merge.

## Compare truth

Every compare operation is scoped to exact:

```text
artifact_id
from_version_id
to_version_id
```

Structured semantic rows include stable node/property identities and before/after values. Raster Artifacts use the same exact version identity while exposing image-oriented visual comparison.

## Approval truth

Historical `APPROVED` versions are not mutated by Restore or later edits. Any continuation is a new DRAFT ArtifactVersion.

## Provenance safety

Safe Provenance contains user-relevant identities/hashes only:

- creator;
- run/task/generation;
- model/provider;
- recipe/skills;
- source Asset/ArtifactVersion IDs;
- BrandRuleSet version;
- quality checks;
- prompt hash/template version;
- constraint hash;
- Git/compiler identity.

It deliberately excludes raw prompt text, system prompt, chain-of-thought, raw tool payloads, stack traces, secrets and signed storage URLs.

Permission denial is represented as `PROVENANCE_FORBIDDEN` and hidden data is not substituted.

## Concurrency truth

A simulated collaborator can append a newer main-branch head. UI shows the newer version and warning while retaining the user's selected Before/After exact versions.

## Unit coverage staged

- branch normalization/invalid branch names;
- safe provenance allowlist;
- Restore creates new DRAFT v5;
- old APPROVED version preserved;
- later history preserved;
- DERIVED_FROM restore lineage;
- stale expected head fails before mutation;
- exact Fork branch;
- exact Design semantic compare;
- concurrent head/history preservation;
- Raster history/compare;
- Provenance permission denial.

## Browser coverage staged

- timeline + HEAD + APPROVED badges;
- Design IR exact semantic compare;
- Restore v2 → new DRAFT v5;
- later v4 and approved v2 remain visible;
- exact v3 Fork;
- concurrent v5 without v2/v4 compare retarget;
- Raster Wipe;
- safe Provenance fields;
- restricted Provenance;
- mobile layout.

## Static architecture gate

```text
python scripts/validate_versions_ui.py
```

The validator checks NODE-42 ownership, ArtifactEngine usage, pre-mutation CAS, append-only Restore, canonical Fork, exact compare, safe Provenance, concurrency behavior, absence of browser durable version truth and required browser/unit coverage markers.

## Hosted workflow

`.github/workflows/versions-ui.yml` stages:

```text
versions-contract
versions-quality
versions-build
versions-browser-e2e
```

Pinned toolchain follows the frontend chain:

```text
Ubuntu 24.04
Node 24
pnpm 11.4.0
Python 3.12
```

## Hosted evidence

Implementation SHA:

```text
6d393e82d013728376fc9319cc8f6b415d1bbfb0
```

Versions UI workflow:

```text
run id: 31866209073
run number: 1
status: completed
conclusion: failure
```

Jobs observed:

```text
versions-contract       94967606694  failure  steps=null
versions-build                        skipped  steps=null
versions-quality                      skipped  steps=null
versions-browser-e2e                  skipped  steps=null
```

GitHub check annotation for `versions-contract` states:

```text
The job was not started because recent account payments have failed or your spending limit needs to be increased. Please check the 'Billing & plans' section in your settings
```

Therefore the GitHub-hosted runner did **not** start. NODE-59's static validator, TypeScript checks, unit tests, lint, production build and Playwright scenarios did not execute on hosted infrastructure.

Correct classification:

```text
hosted pinned gates = BLOCKED BEFORE RUNNER
```

This is a GitHub account billing/spending-limit platform blocker. It is **not** a code/test failure and it is **not** a PASS.

## Production dependencies

Still required for full completion:

- persistent NODE-42 Artifact/Version/Branch/Lineage services;
- transactional branch-head CAS;
- production semantic-diff pipeline;
- real Design/Raster previews;
- approval/quality projection;
- authorization-aware safe Provenance service;
- concurrent event/head integration;
- production tenant isolation and observability.

## Current verdict

```text
Versions route                         IMPLEMENTED
canonical Artifact SDK reuse          IMPLEMENTED
immutable timeline                    IMPLEMENTED
Design IR semantic compare            IMPLEMENTED
Raster side-by-side/overlay/wipe      IMPLEMENTED
append-only Restore                   IMPLEMENTED
pre-mutation branch CAS               IMPLEMENTED
exact historical Fork                 IMPLEMENTED
approved-history immutability         IMPLEMENTED
safe Provenance projection            IMPLEMENTED
provenance permission handling        IMPLEMENTED
concurrent-head notice                IMPLEMENTED
unit/browser coverage                 STAGED
static architecture gate              STAGED
hosted pinned gates                   BLOCKED BEFORE RUNNER
production NODE-42 services           INTEGRATION DEPENDENCY
```

NODE-59 is **IMPLEMENTED / VALIDATING / NOT COMPLETE**.
