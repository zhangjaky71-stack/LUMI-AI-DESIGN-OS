# LUMI Workflow / Recipe Engine V1

> NODE-32 runtime contract  
> Scope: versioned design workflow skeletons, safe compilation, bounded orchestration policy  
> Downstream runtime owner: NODE-33 Task Graph

## 1. Purpose

A Recipe is the deterministic business skeleton around adaptive Agent work.

```text
Recipe = stable orchestration policy
Agent  = adaptive reasoning inside an allowed step
TaskGraphTemplate = immutable compiled handoff to NODE-33
```

The Recipe Engine prevents every Agent run from inventing a new business process from scratch. It makes approvals, quality gates, parallel fan-out, bounded loops, budgets, Agent/Skill versions, and finalization policy explicit and reviewable before execution.

NODE-32 does **not** implement a second durable scheduler. It compiles a versioned Recipe into `TaskGraphTemplate`; NODE-33 owns durable task state, scheduling, retry, cancellation, ready-task selection, and run recovery.

## 2. Source of truth

Canonical Recipe definitions live in Git:

```text
recipes/
  registry.json
  <recipe-id>/
    <exact-version>/
      recipe.yaml
```

P0 uses JSON syntax inside `recipe.yaml`. JSON is valid YAML 1.2 and allows the loader to remain stdlib-only.

Formal DSL schema:

```text
schemas/recipe/recipe.schema.json
```

Release benchmark profiles:

```text
evals/profiles/recipes/registry.json
```

Changing Recipe semantics requires a new exact version. A Project/Agent run freezes the exact Recipe version and definition hash before NODE-33 execution begins.

## 3. Step types V1

Exactly nine step types are allowed:

```text
DETERMINISTIC
AGENT
PARALLEL
FOREACH
APPROVAL
QUALITY_GATE
MEDIA_JOB
SUBRECIPE
FINALIZE
```

There is deliberately no `SCRIPT`, `SHELL`, `SQL`, arbitrary callback, or provider-native invocation step.

Complex deterministic behavior must live in a tested registered service and be referenced by a service key. Paid media work must use a registered media operation.

## 4. P0 registered operations

Deterministic services:

```text
artifact.finalize
campaign.finalize
project.finalize
quality.evaluate
```

Media operations:

```text
image.generate
image.edit
video.generate
export.render
```

These are symbolic registered operations. A Recipe cannot embed provider credentials, provider SDK calls, host commands, SQL, or arbitrary network endpoints.

## 5. Reference binding

A step may read only explicit references:

```text
$inputs.<declared-input>
$project.<field>
$run.<field>
$steps.<upstream-step>.output[.<field>...]
```

`$steps` references are checked against the transitive dependency closure. A step cannot read a future step or an unrelated sibling merely because the name exists elsewhere in the Recipe.

Top-level outputs are also references and are validated against declared steps.

This gives NODE-33 a deterministic dataflow contract rather than hidden prompt-to-prompt coupling.

## 6. Safe condition DSL

V1 conditions use a restricted expression language parsed with Python AST, but never executed through Python `eval()`.

Example:

```text
steps.critic.score < 80 and run.repair_allowed
```

Allowed operations:

```text
roots: inputs, project, steps, run
attribute reads
constants
and / or / not
== != < <= > >=
in / not in
is / is not
literal list / tuple
```

Forbidden examples:

```text
function calls
subscripts
arithmetic expressions
private attributes
imports
assignment
comprehensions
Python or JavaScript execution
```

The evaluator recursively interprets only the validated allowlisted AST nodes.

## 7. DAG validation

Before compilation, the Engine checks:

- every `depends_on` target exists;
- no step depends on itself;
- the dependency graph is acyclic;
- step IDs are unique;
- references point only to valid upstream sources;
- output references resolve to declared steps.

Compilation uses a deterministic topological order.

## 8. Agent and Skill resolution

An `AGENT` step is resolved through NODE-30 `AgentRegistry`.

The compiled task freezes:

```text
requested Agent ref
exact Agent version
Agent definition hash
Agent provenance hash
```

NODE-32 never instantiates a provider-native model or arbitrary tool.

Skill behavior is intentionally non-escalating. NODE-32 first consumes the exact Skill dependencies already frozen by NODE-30/NODE-31. If a Recipe explicitly lists a Skill, that Skill must:

1. be declared by the Agent definition;
2. exist in the Agent's resolved Skill dependency set;
3. resolve to exactly the same frozen Skill version.

Therefore a Recipe cannot give an Agent a new Skill, Tool, permission, or model capability.

## 9. Parallel

A `PARALLEL` container must declare:

```text
max_parallel
join_policy: ALL | ANY | MIN_SUCCESS
budget_limit_usd
budget_split
```

P0 requires the split count to match the number of children and requires the Decimal sum of all child budgets to exactly equal the container budget.

Parallel children are restricted to atomic Agent, deterministic-service, or media-job steps in V1. They cannot hide another arbitrary nested orchestration tree.

Compilation expands children to deterministic task keys:

```text
renders.hero
renders.detail
renders.context
```

and emits a join task with the original step key:

```text
renders
```

Downstream steps therefore depend on the stable join step, not on implementation-specific child ordering.

## 10. Foreach

V1 `FOREACH` is compile-time bounded fan-out.

Rules:

```text
1 <= count <= 8
one atomic template
no local dependency graph inside the template
optional group budget
```

Example task keys:

```text
concepts[0]
concepts[1]
concepts[2]
concepts
```

If a group budget is declared, the compiler divides it deterministically across the fixed count. The join task uses `ALL` in V1.

There is no unbounded dynamic collection expansion in NODE-32.

## 11. Loops

A loop policy is never open-ended.

```text
1 <= max_iterations <= 5
optional positive budget_limit_usd
optional safe stop_condition
```

The loop policy is compiled into Task metadata for NODE-33. NODE-32 does not execute a free-running autonomous loop.

## 12. Approval

An `APPROVAL` step declares:

```text
prompt_summary
allowed_actions
artifact_refs / option_refs
optional expiry
resume_mapping
```

Compilation produces a human-owned Task with metadata bound to:

```text
interrupt_hook = NODE-28:approval_interrupt
decision_authority = LUMI_APPROVAL_SERVICE
```

The Recipe itself does not decide approval. The user/client resume value is not automatically trusted. Durable approval authorization remains LUMI-owned, consistent with NODE-28's policy-resume boundary.

A business rejection can be a valid authorized resume value so the workflow can follow a rejection branch; “authorized resume” and “approved business decision” are distinct concepts.

## 13. Quality gate

A quality gate declares:

```text
metrics
thresholds
optional repair_recipe
max_repair_iterations <= 3
```

Quality evaluation resolves to registered deterministic service `quality.evaluate`.

If a repair Recipe is referenced, it is resolved to an exact Recipe version. Direct self-recursion is rejected. Repair iteration count is bounded at definition construction.

The Critic is therefore not allowed to retry itself indefinitely.

## 14. Subrecipe

`SUBRECIPE` resolves the requested Recipe reference through the same versioned Recipe Registry and freezes the exact version/content hash.

Direct self-inclusion is rejected. V1 deliberately does not attempt arbitrary recursive Recipe expansion in the compiler; NODE-33 receives a bounded exact subrecipe task contract.

## 15. Budget propagation

Budgets are strings parsed as finite positive `Decimal` values. Float-based money values are not used for orchestration accounting.

Budget controls exist at:

```text
Recipe
step
Parallel container + exact child split
Foreach group / per-item derived budget
Loop policy
```

NODE-32 propagates budget ceilings into `TaskGraphTemplate`. Provider cost truth and reservation/accounting remain the existing NODE-27/NODE-22/NODE-20 boundaries.

## 16. TaskGraphTemplate handoff

Compilation produces immutable `TaskGraphTemplate`:

```text
recipe_id
recipe_version
recipe_budget_limit_usd
TaskTemplate[]
outputs
metadata
content_hash
```

Each task contains:

```text
task_key
recipe_step_id
step_type
owner
depends_on
input_bindings
output_schema
condition
budget_limit_usd
bounded metadata
```

Graph metadata includes:

```text
recipe_definition_hash
node33_contract = TaskGraphTemplate:v1
```

NODE-33 is expected to persist an instantiated graph/run binding without replacing these exact provenance fields with “latest”.

## 17. Recipe provenance

`RecipeProvenance` freezes:

```text
requested Recipe ref
exact Recipe id/version
Recipe definition hash
release manifest revision
exact Agent bindings
exact Skill bindings
exact subrecipe identities
TaskGraphTemplate hash
```

`freeze_hash` is a deterministic SHA-256 over this evidence.

Recompiling the same exact repository state must produce the same TaskGraph and provenance hashes.

## 18. Release governance

`recipes/registry.json` separates mutable release status/aliases from immutable version directories.

Statuses:

```text
DRAFT
CANDIDATE
PRODUCTION
DEPRECATED
DISABLED
```

Range selectors resolve only PRODUCTION versions. Exact DEPRECATED versions remain available for historical audit/resume. DRAFT/DISABLED exact versions are not runnable.

Production promotion requires:

1. target status is CANDIDATE;
2. declared eval profile is registered;
3. exact candidate compiles successfully;
4. compiled content hash matches the candidate definition;
5. benchmark/eval gate passes with evidence.

Promotion then deprecates the previous production version, marks the candidate production, stores evidence, moves the `production` alias, and increments manifest revision.

## 19. Security boundary

Recipe YAML is trusted application configuration, but still parsed fail-closed.

The loader rejects authority-bearing field names such as:

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

It also rejects raw `http://` / `https://` values and strings beginning with SQL command verbs inside Recipe definitions.

The Recipe Engine package must not import:

```text
provider SDKs
DB drivers / ORM
requests
subprocess
Docker control
```

The package is a compiler/control-plane module, not an execution authority.

## 20. Initial production Recipes

### quick-image

Direction → image generation → Critic → finalization.

### poster-campaign

Research → direction → three bounded concepts → human approval → polish → Critic → finalization.

### brand-identity

Research → strategy/direction → three bounded moodboards → human approval → identity system → Critic → finalization.

### product-visuals

Direction → three budgeted parallel renders → Critic → quality gate → human approval → finalization.

### social-kit

Direction → three budgeted parallel format adaptations → Critic → finalization.

### image-edit

Direction/protected scope → approval → image edit → Critic → finalization.

### video-campaign

Research → direction → storyboard → approval before paid video generation → video generation → Critic → quality gate → finalization.

## 21. Acceptance model

NODE-32 acceptance has three layers:

1. **Contract** — DSL load, safe-expression tests, DAG tests, release tests, static authority scan, revalidation of NODE-31.
2. **Quality** — frozen workspace, Recipe unit tests, real NODE-23/25/30/31 compiler integration, Ruff, Pyright.
3. **Mock E2E** — compile a real production Recipe and execute the compiled TaskGraph with a deterministic no-provider/no-network mock executor to prove dependency order, bindings, approval mapping, join behavior, and final output resolution.

## 22. Explicit V1 limitations

NODE-32 does not claim:

- persistent task scheduling;
- database-backed TaskGraph instances;
- dynamic unbounded foreach;
- arbitrary nested parallel orchestration;
- arbitrary code execution;
- direct provider/network/database authority;
- runtime retry/cancellation policy ownership;
- durable Approval storage;
- customer billing.

Those responsibilities remain existing boundaries or NODE-33+.

## 23. Handoff to NODE-33

NODE-33 should treat `TaskGraphTemplate` and Recipe provenance as immutable source contracts and add:

```text
TaskGraph instance
TaskInstance state
ready-task selection
parallel scheduling
retry/cancel
checkpoint/recovery
per-task runtime cost/status
```

without changing the semantic meaning of the Recipe that produced the graph.
