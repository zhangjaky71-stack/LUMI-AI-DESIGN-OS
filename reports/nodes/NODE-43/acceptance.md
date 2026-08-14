# NODE-43 Acceptance — Brand Rules Engine

Status: **IMPLEMENTED / VALIDATING / not COMPLETE**

Base: `node-42-artifact-engine-release`

## Scope evidence

| Requirement | Evidence | Engineering status |
|---|---|---|
| Versioned BrandProfile / tokens / assets / rules | `packages/brand-rules/src/types.ts`, `db/migrations/0002_brand_rules.sql` | Implemented |
| HARD / SOFT / ADVISORY | TS + Python rule models/runtime | Implemented |
| Inferred extraction cannot silently become HARD | `extraction.ts`, `extraction.py`, SQL CHECK/trigger | Implemented |
| Extraction citations + human review | TS/Python extraction governance + DB proposal tables | Implemented |
| Deterministic color rules | `runtime.ts`, `runtime.py` | Implemented |
| Typography + font rights | `runtime.ts`, `runtime.py`, NODE-18 adapter inputs | Implemented |
| Logo geometry / clear space | TS/Python deterministic runtime | Implemented |
| Token binding / spacing | TS runtime + DesignOperation repair proposals | Implemented |
| Asset verification boundary | runtime accepts verified asset ids; bytes stay NODE-18 | Implemented |
| Voice structured rules | BrandVoice + forbidden-term deterministic check | Implemented |
| Visual style soft/advisory boundary | BrandVisualReferenceSet, documented grader boundary | Implemented |
| Pinned Agent BrandContext | `packages/brand-rules/src/context.ts`, Python parity | Implemented |
| NODE-39 BrandComplianceValidator | `constraint-adapter.ts` | Implemented |
| Validator-unavailable fail closed | `constraint-adapter.test.ts` | Implemented |
| NODE-38-only repair mutation | diagnostics emit `DesignOperation[]` only | Implemented |
| NODE-42 approval gate | `artifact-gate.ts` | Implemented |
| Exact artifact brand rule version | Artifact SDK + Python artifact model + migration | Implemented |
| Tenant-aware persistence | composite org keys in migration | Implemented |
| TS conformance tests | `brand-rules.test.ts`, `constraint-adapter.test.ts` | Implemented; hosted execution pending |
| Python conformance tests | `services/brand-rules/tests/test_brand_rules.py` | Implemented; hosted execution pending |
| Static contract validator | `scripts/validate_brand_rules_engine.py` | Implemented; hosted execution pending |
| 2k/40 deterministic benchmark | `scripts/benchmark_brand_rules_engine.py` | Implemented; hosted measurement pending |
| Dedicated CI | `.github/workflows/brand-rules-engine.yml` | Implemented; hosted execution pending |

## Frozen architecture assertions

1. Brand Engine does not create a second Design IR mutation protocol.
2. Brand Engine does not bypass NODE-39 hard-constraint enforcement.
3. Repair proposals are NODE-38 DesignOperations with `expected_document_version`.
4. Binary assets, MIME/scanning and font licensing remain NODE-18 responsibilities.
5. Approved brand facts are structured/pinned inputs to NODE-34; memory does not override them.
6. Artifact history records the exact brand rule version; new rule publications do not rewrite old versions.
7. Model-extracted guide content is data/proposal until explicitly reviewed.
8. Deterministic geometry/token checks do not default to an LLM/VLM.
9. Semantic visual identity remains NODE-44 territory.

## Test cases implemented

- forbidden color -> hard diagnostic + repair proposal;
- disallowed/unlicensed font -> fail with allowed replacement when available;
- logo rotation and clear-space violations;
- minimum text size and spacing-scale warnings;
- unbound brand token -> structured SET_PROPERTY proposal;
- inferred HARD rule rejection;
- guide extraction requires citation;
- reviewer can intentionally promote approved cited rule to HARD;
- stale token/asset version -> evaluation error, never silent PASS;
- ArtifactVersion/report brand-version mismatch -> approval denied;
- NODE-39 adapter maps brand diagnostics;
- resolver outage -> `VALIDATION_UNAVAILABLE` hard violation.

## Hosted validation

At the time this report was authored, NODE-43 had not yet been published as its release PR, so no dedicated hosted run is claimed here.

Completion requires all of these to **actually execute green**:

```text
brand-contract
brand-quality
brand-integration
brand-benchmark
```

If GitHub Actions is prevented from starting by the repository/account billing or spending-limit condition observed on preceding nodes, record the exact annotation as an **external CI blocker**. Do not relabel the node PASS, COMPLETE, or code-failed from a zero-step runner failure.

## Current decision

**IMPLEMENTED / VALIDATING / not COMPLETE**

Next: NODE-44 Identity Engine after NODE-43 release evidence is recorded.
