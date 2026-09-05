# LUMI Skill Registry V1

> NODE: 31  
> Phase: 4 — Agent Intelligence  
> Status: IMPLEMENTED / VALIDATING  
> Depends on: NODE-29 Deep Agents Runtime, NODE-30 Agent Registry

## 1. Purpose

NODE-31 turns reusable Agent know-how into immutable, versioned Skill packs rather than large prompts copied into every Agent.

The canonical source is:

```text
skills/<skill-id>/<semver>/skill.yaml
skills/<skill-id>/<semver>/SKILL.md
skills/<skill-id>/<semver>/<optional-resources>
```

`skill.yaml` uses JSON syntax, a valid YAML 1.2 subset, keeping P0 loading deterministic without another YAML dependency.

## 2. Control-plane boundary

LUMI Skill Registry owns:

- exact Skill version resolution;
- release status and production aliases;
- Agent compatibility;
- Tool/permission/model-capability non-escalation;
- dependency DAG resolution;
- cycle/version-conflict detection;
- minimal task-based selection;
- schema/eval references;
- release gates;
- deterministic Skill-pack provenance.

Deep Agents owns only the runtime progressive-disclosure mechanism after LUMI has selected the exact pack.

The supported path is:

```text
Task + Agent runtime scope
→ SkillSelector / explicit Skill requirement
→ SkillRegistry exact-version DAG
→ compatibility/tool/permission/capability checks
→ DeepAgentsSkillBundle
→ only selected files under /skills/
→ create_deep_agent(..., skills=["/skills/"])
```

The system never points Deep Agents at the whole repository.

## 3. SkillDefinition

Each immutable SkillDefinition freezes:

```text
id
version
summary
compatible_agents
required_tools + version constraints
required_capabilities
input_schema
output_schema
permissions
dependencies
eval_profile
task_types
SKILL.md hash
resource hashes
metadata
```

The resulting content hash changes when executable knowledge, dependencies, schemas, permissions, capability requirements or resources change.

## 4. Deep Agents SKILL.md contract

Every committed Skill has frontmatter:

```md
---
name: <skill-id>
description: <summary>
---
```

Loader rules require frontmatter name and description to match `skill.yaml` exactly. Description is bounded to the current Deep Agents limit used by this runtime.

Every P0 Skill contains:

- `## When to use`
- `## Required inputs`
- `## Step sequence`
- `## Design heuristics`
- `## Constraints`
- `## Verification checklist`
- `## Failure modes`
- `## Examples`
- `## What not to do`

Examples carry explicit rights provenance in `skill.yaml`: `synthetic`, `owned`, or `licensed`. P0 examples are synthetic.

## 5. Resource safety

Skill resources are UTF-8 text only in P0.

Runtime rejects:

- absolute paths;
- `..` traversal;
- backslash path escapes;
- empty/dot path components;
- non-UTF-8 resources;
- more than 128 resources;
- SKILL.md over 10 MiB;
- total Skill payload over 16 MiB.

Large binary design media remains Asset/Artifact data, not a Skill resource.

## 6. Release states and SemVer

Release states:

```text
DRAFT
CANDIDATE
PRODUCTION
DEPRECATED
DISABLED
```

Resolution supports exact SemVer, major selectors, caret/tilde ranges and aliases such as `production`.

Rules:

- ranges select only PRODUCTION;
- `production` must point to PRODUCTION;
- exact DEPRECATED remains available for historical replay/resume;
- exact DRAFT/DISABLED is not runnable;
- at most one PRODUCTION release exists per Skill in P0.

The committed catalog contains 14 Skill IDs and 15 exact versions because `creative-direction` retains both 1.0.0 DEPRECATED and 1.1.0 PRODUCTION.

## 7. P0 Skill catalog

Production Skill IDs:

```text
brief-normalization
web-research
brand-strategy
creative-direction
moodboard
poster-design
typography
layout
image-generation
image-edit
product-render
visual-critique
brand-consistency
export-social
```

`creative-direction@^1` resolves 1.1.0. Exact 1.0.0 remains DEPRECATED history.

## 8. Dependency DAG

Skill dependencies are semantic version requirements. Registry resolves them to exact releases before execution.

Representative graph:

```text
poster-design
├─ creative-direction
│  ├─ brand-strategy
│  │  ├─ brief-normalization
│  │  └─ web-research
│  └─ brief-normalization
└─ layout
   └─ typography
      └─ brief-normalization
```

Resolution is dependency-first and deduplicates the same exact Skill.

Fail-closed cases:

- dependency cycle;
- one pack resolving two exact versions of the same Skill id;
- missing release;
- disabled/draft exact dependency.

## 9. Minimal Skill selection

`SkillSelector` does not expose every Skill to every task.

A candidate must match:

- task type;
- compatible Agent;
- PRODUCTION release;
- explicit `selector_primary=true`.

Exactly one primary candidate is required. The Registry then adds only that Skill's dependency DAG.

Example: `poster-design` loads seven relevant Skill IDs and does not load image-edit/product-render/brand-consistency.

## 10. Agent compatibility and permission non-escalation

Before a selected pack is run, every Skill is checked against `SkillExecutionContext`.

```text
Skill.compatible_agents contains Agent
Skill.required_tools ⊆ Agent allowed tools
Skill.permissions ⊆ granted permissions
Skill.required_capabilities ⊆ available capabilities
```

A Skill is knowledge/configuration; it cannot grant new Tools, permissions or model capabilities.

`AgentSkillCompatibilityValidator` also plugs into NODE-30's optional `AgentSkillPolicy` so Agent release validation can reject incompatible declared Skills.

## 11. NODE-30 Skill bootstrap replacement

NODE-30 introduced a temporary Skill bootstrap catalog because NODE-31 did not exist yet.

NODE-31 replaces that execution path with `Node31SkillCatalog`:

```text
Skill requirement
→ NODE-31 exact release
→ exact version
→ real Skill content hash
→ source_ref NODE-31:<skill-id>@<version>
```

The NODE-30 integration acceptance asserts `creative-direction@^1` freezes `1.1.0` with its real NODE-31 content hash and contains no bootstrap source reference.

The remaining NODE-30 bootstrap catalogs for Context/Budget/output/eval are separate future-node adapters and are not Skill resolution.

## 12. Model capability validation

Skill capabilities use the same vocabulary as Model Gateway.

P0 media examples include:

```text
image-generation -> image.generate
image-edit       -> image.edit
product-render   -> image.generate
```

Unknown capability names fail release validation. Missing available capability fails selected-pack execution before the run starts.

## 13. Tool validation

Required Tools resolve through the NODE-25 Tool Registry and exact Tool versions are validated before a Skill release can pass definition validation.

No Skill can introduce an unrestricted SQL tool or arbitrary callable. Execution still goes through NODE-25 Tool Gateway with its risk/HITL/idempotency/audit boundary.

## 14. Schema contracts

Canonical Skill I/O schemas live under:

```text
schemas/skill-io/
```

Registry IDs:

```text
GenericTaskInput
PlanOutput
ResearchOutput
ReviewOutput
MediaOutput
ExportOutput
```

`SkillDefinitionValidator` requires every Skill input/output schema reference to resolve in the schema registry.

## 15. Eval profiles and promotion

Canonical Skill eval policy lives in:

```text
evals/profiles/skills/registry.json
```

Every profile declares:

- schema correctness;
- task success;
- regression sample requirement;
- cost/latency guard;
- whether human review is required.

Design/media/review Skills require human review in P0. Brief normalization and web research can use automatic release review.

PRODUCTION release metadata must contain passed eval evidence.

`SkillPromotionManager` promotes only a CANDIDATE after:

1. `SkillDefinitionValidator` passes Tool/schema/eval/capability/document checks;
2. `SkillEvalGate` returns passed evidence.

Promotion deprecates the prior production release, moves the production alias and increments manifest revision.

## 16. Progressive disclosure

`DeepAgentsSkillBundle` converts only the exact resolved pack to virtual files:

```text
/skills/<skill-id>/SKILL.md
/skills/<skill-id>/<resources>
```

It uses the current Deep Agents `create_file_data` helper when building StateBackend-compatible files.

The Skill-aware compiler requires the installed `create_deep_agent` signature to support `skills`; it does not silently discard Skill configuration on SDK drift.

Runtime call:

```text
create_deep_agent(..., skills=["/skills/"])
```

Deep Agents can then inspect frontmatter and read complete Skill instructions on demand. LUMI has already reduced the visible set to the exact selected pack.

## 17. Pack provenance

`ResolvedSkillPack.freeze_hash` freezes:

- root references;
- Skill release-manifest revision;
- dependency-first exact Skill ids/versions;
- content hashes;
- release status.

`SkillAwareDeepAgentCompiler` copies:

```text
skill_pack_freeze_hash
resolved_skills[id, version, hash]
```

into NODE-29/NODE-28 GraphDefinition metadata.

A later production alias change therefore cannot rewrite an already compiled/run pack's provenance.

## 18. Current Deep Agents integration

`scripts/integration_skill_registry_deep_agents.py` uses:

- real current `create_deep_agent`;
- explicit `skills=["/skills/"]`;
- current StateBackend virtual files;
- current `create_file_data`;
- LangGraph InMemorySaver;
- deterministic NODE-22-marked test model;
- no live provider credentials.

The integration injects only `brief-normalization@1.0.0`, verifies pack provenance in GraphDefinition, runs the compiled graph and expects `NODE31_SKILL_OK`.

## 19. All-production pack acceptance

`scripts/integration_skill_registry_pack.py` resolves every PRODUCTION Skill twice under a compatible synthetic execution context.

It requires:

- 14 production roots;
- no cycles;
- no duplicate Skill id inside a pack;
- root exact version is final in dependency-first ordering;
- no DISABLED dependency;
- identical freeze hash across repeated resolution.

## 20. Security boundary

`skill_registry` is declarative/runtime composition code and is statically scanned for ambient authority. Direct asyncpg/SQLAlchemy/provider SDK/requests/subprocess/Docker imports are forbidden.

Skills do not get credentials, direct provider clients or host shell access. They can only request capabilities already exposed by the Agent/Model/Tool boundaries.

## 21. CI

Dedicated `.github/workflows/skill-registry.yml` uses three sequential gates:

1. `skill-registry-contract` — compile, NODE-25/NODE-29/NODE-30 revalidation, static contract, pure unit tests;
2. `skill-registry-quality` — frozen workspace, pytest, NODE-30→NODE-31 integration, current Deep Agents Skill integration, promotion validation, Ruff/Pyright;
3. `skill-registry-pack` — all 14 production packs resolve deterministically.

Hosted PASS is not claimed until all required jobs receive a runner and execute green.

## 22. P0 limitations

Deliberately deferred:

- remote Skill package download;
- binary Skill resources;
- arbitrary executable scripts from untrusted packages;
- automatic multi-primary Skill selection;
- customer-authored Skill marketplace;
- distributed Skill rollout/canary UI;
- permanent Context/Memory registries;
- NODE-32 workflow/recipe orchestration.

## 23. Definition of Done boundary

NODE-31 scope is immutable Git Skill packs + release metadata + SemVer/DAG resolution + minimal selection + Agent/tool/permission/capability non-escalation + schema/eval gates + progressive-disclosure Deep Agents binding + pack provenance + 14 P0 Skills + tests/docs/CI.

Status remains `IMPLEMENTED / VALIDATING / not COMPLETE` until hosted required gates are green.
