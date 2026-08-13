# NODE-31 Acceptance — Skill Registry

> Branch: `node-31-skill-registry-impl`  
> Base: `node-30-agent-registry`  
> Status: **IMPLEMENTED / VALIDATING / not COMPLETE**

## Acceptance matrix

- [x] Git-versioned `skills/<id>/<version>/skill.yaml + SKILL.md`
- [x] 14 P0 Skill IDs / 15 exact versions
- [x] exact SemVer/range/production alias resolution
- [x] range selectors choose only PRODUCTION
- [x] exact DEPRECATED remains resolvable
- [x] dependency-first deterministic DAG
- [x] cycle detection
- [x] same-id exact-version conflict detection
- [x] compatible Agent guard
- [x] required Tool subset guard
- [x] permission subset guard
- [x] model capability subset guard
- [x] minimal task selector
- [x] no whole-registry Skill loading
- [x] SKILL.md frontmatter validation
- [x] required instructional sections
- [x] synthetic/owned/licensed example-rights policy
- [x] UTF-8 text-only P0 resources and traversal guards
- [x] canonical Skill I/O schema registry
- [x] canonical Skill eval profile registry
- [x] CANDIDATE promotion requires definition validation + eval evidence
- [x] NODE-30 `AgentValidator` Skill-policy hook
- [x] NODE-31 replaces NODE-30 bootstrap Skill dependency resolution
- [x] selected exact pack exposed under `/skills/`
- [x] current Deep Agents `skills=["/skills/"]` compile path
- [x] exact Skill pack provenance frozen into GraphDefinition
- [x] deterministic tests, integrations, docs and CI authored

## P0 catalog

Production roots:

```text
brief-normalization
web-research
brand-strategy
creative-direction@1.1.0
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

Historical exact release:

```text
creative-direction@1.0.0 DEPRECATED
```

## DAG acceptance

`poster-design@^1` resolves dependency-first to:

```text
brief-normalization
web-research
brand-strategy
creative-direction
typography
layout
poster-design
```

The pack does not include unrelated `image-edit`, `product-render`, or `brand-consistency` Skills.

## Permission and capability acceptance

`SkillRegistry.resolve_pack()` verifies every dependency, not only the root:

```text
Agent compatibility
required_tools ⊆ allowed_tools
Skill permissions ⊆ granted permissions
required_capabilities ⊆ available capabilities
```

Tests prove missing web Tool scope blocks moodboard and missing `image.generate` blocks image-generation before execution.

## NODE-30 replacement acceptance

`scripts/integration_skill_registry_agent.py` uses real:

- NODE-23 Capability Registry;
- NODE-25 Tool Registry;
- NODE-31 Skill Registry;
- NODE-30 Agent Registry.

The resolved Creative Director Skill provenance must be:

```text
creative-direction
exact_version = 1.1.0
content_hash = real NODE-31 SkillDefinition hash
source_ref = NODE-31:creative-direction@1.1.0
```

The integration explicitly rejects bootstrap Skill provenance.

## Deep Agents progressive-disclosure acceptance

`DeepAgentsSkillBundle` seeds only the resolved exact pack as:

```text
/skills/<id>/SKILL.md
/skills/<id>/<resource>
```

`scripts/integration_skill_registry_deep_agents.py` verifies the installed current Deep Agents API accepts `skills=["/skills/"]`, StateBackend receives the selected virtual files, GraphDefinition contains the exact pack freeze hash and the deterministic run returns `NODE31_SKILL_OK`.

No live provider credential is required.

## Release acceptance

Every committed PRODUCTION Skill has `eval_status=passed` plus evidence. Every release eval profile must match the SkillDefinition.

`SkillDefinitionValidator` validates document sections, example rights, required Tool versions, input/output schemas, eval profile and capability vocabulary.

`SkillPromotionManager` allows only CANDIDATE promotion and requires both definition validation and a passing `SkillEvalGate`. Unit tests include passing and failing eval cases.

## Tests

```text
apps/agent-runtime/tests/test_skill_registry.py
apps/agent-runtime/tests/test_skill_deep_bundle.py
apps/agent-runtime/tests/test_skill_release.py
```

## Integrations

```text
scripts/integration_skill_registry_agent.py
scripts/integration_skill_registry_deep_agents.py
scripts/integration_skill_registry_pack.py
```

## Static architecture contract

`scripts/validate_skill_registry_contract.py` verifies:

- 14 IDs / 15 versions;
- all definitions pass release validation;
- production eval evidence;
- DAG/selection/non-escalation code markers;
- Deep Agents selected-pack-only binding;
- current `skills` parameter requirement;
- NODE-30 Skill policy hook;
- real NODE-31 provenance in Agent integration;
- no bootstrap Skill path in that integration;
- no ambient DB/provider/network/shell authority in Skill Registry runtime.

## CI

Required jobs:

1. `skill-registry-contract`
2. `skill-registry-quality`
3. `skill-registry-pack`

No hosted PASS is claimed until all required jobs execute green on a real runner.

If GitHub again returns `steps=[]`, `runner_id=0`, blank runner and the account payment/spending-limit annotation, NODE-31 is classified:

```text
IMPLEMENTED / VALIDATING / BLOCKED_EXTERNAL / not COMPLETE
```

A runner-started test failure is an engineering defect and must be fixed before COMPLETE.

## Stack note

The original `node-31-skill-registry` branch hit repeated connector ref-update uncertainty after a successful generated commit. No force push was used. Work continued linearly from that exact commit on `node-31-skill-registry-impl`, which is the canonical NODE-31 PR head.

## Deferred scope

NODE-32 owns workflow/recipe orchestration. Remote Skill downloads, binary resources, arbitrary untrusted executable scripts, marketplace distribution and broad auto-selection are not claimed by NODE-31.
