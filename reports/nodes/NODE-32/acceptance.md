# NODE-32 — Workflow / Recipe Engine Acceptance

## Status

```text
IMPLEMENTED / VALIDATING / not COMPLETE
```

NODE-32 is not COMPLETE until its own required hosted gates receive real runners and execute green.

No hosted PASS is inferred from source inspection. If a required GitHub Actions job receives no runner and GitHub returns the established payment/spending-limit annotation, that is `BLOCKED_EXTERNAL`, not a code/test failure.

## Implemented scope

- [x] Versioned Recipe DSL runtime contracts.
- [x] Formal `schemas/recipe/recipe.schema.json`.
- [x] Nine allowed Step types; no SCRIPT/arbitrary-code step.
- [x] Git-backed Recipe release registry and production aliases.
- [x] Exact/range/prod Recipe resolution; ranges select only PRODUCTION.
- [x] Exact DEPRECATED historical resolution; DRAFT/DISABLED fail closed.
- [x] Deterministic DAG validation and cycle/missing-dependency rejection.
- [x] Restricted reference binding with upstream-step enforcement.
- [x] Restricted condition AST parser/evaluator with no builtin `eval()`.
- [x] Bounded Loop policy (`max_iterations <= 5`).
- [x] Bounded Parallel policy (`max_parallel <= 8`) with exact Decimal budget split.
- [x] Bounded compile-time Foreach (`count <= 8`).
- [x] Approval metadata bound to NODE-28 interrupt hook and LUMI decision authority.
- [x] Quality gate with bounded repair iterations (`<= 3`).
- [x] SUBRECIPE exact resolution and direct self-recursion rejection.
- [x] NODE-30 Agent exact resolution/provenance freeze.
- [x] NODE-31 Skill exact resolution/non-escalation.
- [x] Registered deterministic-service/media-operation boundary.
- [x] Immutable `TaskGraphTemplate` handoff contract for NODE-33.
- [x] Exact Recipe/Agent/Skill/subrecipe/TaskGraph provenance freeze hash.
- [x] CANDIDATE compile + benchmark/eval gate before PRODUCTION promotion.
- [x] Seven initial production Recipe skeletons.
- [x] Deterministic mock Recipe executor acceptance authored.
- [x] Dedicated static architecture/security validator authored.
- [x] Dedicated NODE-32 CI workflow authored.

## Initial Recipe catalog

```text
quick-image@1.0.0
poster-campaign@1.0.0
brand-identity@1.0.0
product-visuals@1.0.0
social-kit@1.0.0
image-edit@1.0.0
video-campaign@1.0.0
```

Each is currently declared PRODUCTION in `recipes/registry.json` with a passing release-evidence reference and exact `production` alias.

## Security assertions

NODE-32 Recipe definitions cannot directly request execution authority through fields such as:

```text
script
command
shell
sql
raw_url
api_key
provider_key
secret
access_token
private_key
```

The loader also rejects raw HTTP(S) values and SQL-command-like strings in Recipe definitions.

The safe expression engine parses allowlisted AST nodes and does not call Python `eval`, `exec`, or `compile`.

The Recipe Engine runtime package is expected to remain free of provider SDKs, database drivers/ORM, broad HTTP clients, subprocess, and Docker control.

## Required deterministic tests

### Expression / loader security

File:

```text
apps/agent-runtime/tests/test_recipe_expression.py
```

Covers:

- safe boolean/comparison expression;
- function-call rejection;
- subscript rejection;
- arithmetic-code rejection;
- authority-field rejection;
- raw-URL rejection.

### DAG / bounded-loop contract

File:

```text
apps/agent-runtime/tests/test_recipe_dag.py
```

Covers:

- seven initial Recipe definitions;
- production/range resolution;
- bounded loop 1..5;
- missing dependency;
- dependency cycle.

### Release governance

File:

```text
apps/agent-runtime/tests/test_recipe_release.py
```

Covers:

- failed benchmark blocks candidate promotion;
- passing benchmark promotes candidate;
- old production becomes DEPRECATED;
- production alias moves;
- release revision increments;
- eval evidence is persisted.

## Required cross-node integration

File:

```text
scripts/integration_recipe_engine.py
```

It composes real:

```text
NODE-23 Capability Registry
NODE-25 Tool Registry
NODE-30 Agent Registry
NODE-31 Skill Registry
NODE-32 Recipe Registry/Compiler
```

Required assertions include:

- all seven production Recipes compile;
- exact Recipe version is 1.0.0;
- repeated compilation produces stable TaskGraph/provenance hashes;
- quick-image freezes creative-director@1.1.0 and critic@1.0.0;
- quick-image freezes creative-direction@1.1.0 and visual-critique@1.0.0;
- media operations are registered symbolic operations;
- product-visuals parallel children receive 2/2/2 budgets and join at 6;
- approval metadata uses NODE-28 interrupt hook/LUMI authority/resume mapping;
- poster-campaign expands exactly three concept tasks plus join;
- video-campaign freezes `video.generate` and bounded quality policy.

## Required mock E2E

File:

```text
scripts/integration_recipe_engine_mock.py
```

The mock executor:

1. compiles a real production Recipe through the real cross-node registries;
2. executes only the compiled TaskGraph contract;
3. checks every dependency exists before task execution;
4. resolves only compiled `$inputs` / `$steps` references;
5. deterministically simulates Agent/media/Approval/join/service output;
6. resolves the declared final Recipe output;
7. performs no provider, network, database, or paid call.

## Static contract gate

File:

```text
scripts/validate_recipe_engine_contract.py
```

Must enforce:

- exact seven initial Recipes;
- exact nine StepType values;
- production release/evidence expectations;
- DSL schema and Recipe eval-profile registry presence;
- Recipe loader authority guards;
- no builtin eval/exec/compile in runtime package;
- no ambient-authority imports;
- Agent/Skill exact-resolution/non-escalation markers;
- Approval NODE-28/LUMI authority markers;
- Parallel budget-equality marker;
- Foreach upper bound;
- NODE-33 TaskGraphTemplate handoff marker;
- release benchmark/eval promotion marker.

## CI gates

Expected workflow:

```text
Workflow / Recipe Engine
```

Required jobs:

```text
recipe-contract
  -> recipe-quality
     -> recipe-mock
```

### recipe-contract

Expected to run:

- Python compileall for NODE-32 runtime/tests/scripts;
- NODE-31 static Skill Registry revalidation;
- NODE-32 static contract validator;
- dependency-light Recipe unit tests.

### recipe-quality

Expected to run after a frozen workspace install:

- Recipe unit tests through pytest;
- real NODE-23/25/30/31 compiler integration;
- Ruff;
- Pyright.

### recipe-mock

Expected to run:

- real production Recipe compiler integration again as an upstream guard;
- deterministic mock Recipe E2E.

## Boundary / non-goals

NODE-32 intentionally does not claim:

- durable TaskGraph persistence;
- scheduler/worker leasing;
- runtime retry orchestration;
- database-backed task state;
- cancellation propagation;
- arbitrary dynamic fan-out;
- arbitrary nested orchestration;
- durable Approval storage;
- provider-cost ownership;
- customer billing.

Those are existing boundaries or NODE-33+ responsibilities.

## Completion rule

Do **not** change this node to COMPLETE until the NODE-32 required hosted gates have actually executed green on a real runner.
