# LUMI AI Design OS — Lovart Public Capability Matrix v1.0.0

> Competitor: **Lovart**  
> Evidence observation date: **2026-08-12**  
> Revalidated against current official docs: **2026-08-13**  
> NODE: **NODE-06 — Lovart Capability Matrix**  
> Contract manifest: `docs/product/capability-matrix-manifest.json`  
> Evidence catalog: `docs/product/lovart-evidence-sources.json`  
> Acceptance specs: `evals/datasets/product-parity/v1/`

---

## 1. Purpose and legal boundary

This matrix converts the product goal “build a Lovart-class AI Design Agent” into observable, testable product capabilities. It records only public behavior and public claims from Lovart-owned documentation, product/tool pages, statements, changelog, and official blog posts.

It **does not** copy or infer Lovart proprietary source code, prompts, model weights, private architecture, internal datasets, trademarks, or visual assets. `confirmed_marketing` means an official Lovart product/tool/blog page claims the behavior but the reviewed core docs do not provide the same level of operational detail. `not_confirmed` means the reviewed official source set did not provide qualifying evidence; it is not a claim that Lovart lacks the feature internally.

## 2. Snapshot

| Dimension | Count |
|---|---:|
| Categories | 7 |
| Atomic capabilities | 67 |
| Lovart `confirmed` | 56 |
| Lovart `confirmed_marketing` | 9 |
| Lovart `not_confirmed` | 2 |
| LUMI `PARITY` targets | 56 |
| LUMI `SUPERSET` targets | 7 |
| LUMI `DEFER` targets | 4 |
| Product-parity acceptance specs | 56 |

All 67 current LUMI capability gaps are `OPEN` because NODE-06 is a benchmark/specification node; owning implementation Nodes later change each row to `IN_PROGRESS`, `IMPLEMENTED`, and eventually `COMPLETE` only after executable acceptance evidence exists.

## 3. Evidence tiers

| Tier | Meaning |
|---|---|
| 1 | Official docs, statement, or changelog |
| 2 | Official Lovart feature/tool page |
| 3 | Official Lovart blog/product update |

The canonical URLs and evidence descriptions live in `docs/product/lovart-evidence-sources.json`. The matrix references source IDs rather than duplicating URLs in every row.

---

# A. Agent / Workflow

| ID | Public capability | Lovart evidence status | Sources | LUMI target | Owning Nodes | Acceptance |
|---|---|---|---|---|---|---|
| A01 | Natural-language brief to generated asset | confirmed | SRC-GETTING-STARTED | PARITY | NODE-17, NODE-28, NODE-54 | PARITY-A01 |
| A02 | Web research before design | confirmed | SRC-CHAT | PARITY | NODE-25, NODE-34, NODE-36, NODE-54 | PARITY-A02 |
| A03 | Autonomous goal decomposition and planning | confirmed_marketing | SRC-MCOT | PARITY | NODE-28, NODE-29, NODE-37 | PARITY-A03 |
| A04 | Guided workflow that asks for missing details | confirmed | SRC-SKILLS | PARITY | NODE-31, NODE-32, NODE-54 | PARITY-A04 |
| A05 | Multi-step creative Skills | confirmed | SRC-SKILLS | PARITY | NODE-31, NODE-32, NODE-37 | PARITY-A05 |
| A06 | Thinking and Fast interaction modes | confirmed | SRC-CHAT | PARITY | NODE-28, NODE-29, NODE-54 | PARITY-A06 |
| A07 | Continue and revisit project chat sessions | confirmed | SRC-CHAT | PARITY | NODE-35, NODE-54, NODE-57 | PARITY-A07 |
| A08 | Automatic model selection by task | confirmed | SRC-MODELS | PARITY | NODE-22, NODE-23, NODE-24 | PARITY-A08 |
| A09 | Manual model preference and strict model lock | confirmed | SRC-MODELS, SRC-CHAT | PARITY | NODE-22, NODE-23, NODE-54 | PARITY-A09 |
| A10 | Reusable custom Skills distilled from prior conversation | confirmed | SRC-SKILLS | SUPERSET | NODE-30, NODE-31, NODE-32 | Owning Node eval |
| A11 | Voice interaction with design agent | confirmed | SRC-CHAT | DEFER | NODE-54 | Deferred |

**LUMI differentiation:** custom Skills are not just saved workflows; the target is a versioned Skill Registry with dependency, permission, model/tool policy, examples, and eval metadata.

---

# B. Canvas / Editing

| ID | Public capability | Lovart evidence status | Sources | LUMI target | Owning Nodes | Acceptance |
|---|---|---|---|---|---|---|
| B01 | Infinite canvas workspace | confirmed | SRC-CANVAS, SRC-GETTING-STARTED | PARITY | NODE-40, NODE-55 | PARITY-B01 |
| B02 | Multi-artifact project workspace | confirmed | SRC-CANVAS | PARITY | NODE-40, NODE-54, NODE-55 | PARITY-B02 |
| B03 | Select, move and resize canvas elements | confirmed | SRC-CANVAS | PARITY | NODE-40, NODE-55 | PARITY-B03 |
| B04 | Multi-select, group, lock and layer ordering | confirmed | SRC-CANVAS | PARITY | NODE-40, NODE-56 | PARITY-B04 |
| B05 | Layer panel and visibility controls | confirmed | SRC-CANVAS | PARITY | NODE-40, NODE-56 | PARITY-B05 |
| B06 | Per-object history surfaced from layer panel | confirmed | SRC-CANVAS | SUPERSET | NODE-42, NODE-59 | Owning Node eval |
| B07 | Pan, zoom and minimap navigation | confirmed | SRC-CANVAS | PARITY | NODE-55 | PARITY-B07 |
| B08 | Reference assets added to canvas or prompt context | confirmed | SRC-REFERENCES | PARITY | NODE-18, NODE-34, NODE-55 | PARITY-B08 |
| B09 | Generated files browser inside project | confirmed | SRC-CANVAS | PARITY | NODE-18, NODE-54 | PARITY-B09 |
| B10 | Semantic local Touch Edit without manual mask | confirmed | SRC-TOUCH | PARITY | NODE-47, NODE-55 | PARITY-B10 |
| B11 | Edit text in place | confirmed | SRC-CANVAS | PARITY | NODE-40, NODE-56 | PARITY-B11 |
| B12 | Non-destructive variations with revert/compare | confirmed_marketing | SRC-TOUCH, SRC-VERSION | SUPERSET | NODE-42, NODE-59 | Owning Node eval |
| B13 | Quick AI edit actions: upscale/remove BG/crop/expand/eraser/mockup | confirmed | SRC-CANVAS | PARITY | NODE-45, NODE-47, NODE-49, NODE-55 | PARITY-B13 |
| B14 | Multi-angle subject/camera transformation | confirmed | SRC-GETTING-STARTED | PARITY | NODE-45, NODE-47 | PARITY-B14 |

**LUMI differentiation:** editable Canvas operations must resolve to versioned Design IR/Artifact operations; “do not move product/logo/QR” is enforced by Constraint Validator, not just prompt wording.

---

# C. Generation

| ID | Public capability | Lovart evidence status | Sources | LUMI target | Owning Nodes | Acceptance |
|---|---|---|---|---|---|---|
| C01 | Text-to-image generation | confirmed | SRC-GETTING-STARTED, SRC-MODELS | PARITY | NODE-22, NODE-46 | PARITY-C01 |
| C02 | Image-to-image editing | confirmed | SRC-GETTING-STARTED, SRC-TOUCH | PARITY | NODE-47 | PARITY-C02 |
| C03 | Image-to-video generation | confirmed | SRC-GETTING-STARTED, SRC-VIDEO | PARITY | NODE-48 | PARITY-C03 |
| C04 | Text-to-video generation | confirmed | SRC-VIDEO, SRC-MODELS | PARITY | NODE-48 | PARITY-C04 |
| C05 | Product showcase video workflow | confirmed_marketing | SRC-VIDEO | PARITY | NODE-48 | PARITY-C05 |
| C06 | Batch variants from one prompt/brief | confirmed_marketing | SRC-BATCH | PARITY | NODE-32, NODE-46, NODE-48 | PARITY-C06 |
| C07 | Multi-platform aspect-ratio adaptation | confirmed_marketing | SRC-VIDEO, SRC-BATCH | PARITY | NODE-49, NODE-60 | PARITY-C07 |
| C08 | Product/brand mockup workflow | confirmed | SRC-CANVAS, SRC-BRAND | PARITY | NODE-45, NODE-47, NODE-49 | PARITY-C08 |
| C09 | Mixed-model routing and fallback preferences | confirmed | SRC-MODELS | PARITY | NODE-22, NODE-23, NODE-24 | PARITY-C09 |
| C10 | Direct model generator bypassing Agent | confirmed | SRC-MODELS | PARITY | NODE-22, NODE-54 | PARITY-C10 |
| C11 | 3D generation model preference | confirmed | SRC-MODELS | DEFER | NODE-22, NODE-23 | Deferred |

NODE-07 will turn the model-facing rows into a provider/cost/latency/quality benchmark rather than hard-coding Lovart's current provider list.

---

# D. Brand

| ID | Public capability | Lovart evidence status | Sources | LUMI target | Owning Nodes | Acceptance |
|---|---|---|---|---|---|---|
| D01 | Global Brand Kit reusable across tasks, sessions and projects | confirmed | SRC-REFERENCES | PARITY | NODE-35, NODE-43, NODE-58 | PARITY-D01 |
| D02 | Upload logos, fonts, color swatches, photography and brand guidance | confirmed | SRC-REFERENCES | PARITY | NODE-18, NODE-43, NODE-58 | PARITY-D02 |
| D03 | Parse uploaded brand book into Brand Kit | confirmed | SRC-REFERENCES | PARITY | NODE-36, NODE-43, NODE-58 | PARITY-D03 |
| D04 | Apply Brand Kit per generation or whole project | confirmed | SRC-REFERENCES | PARITY | NODE-34, NODE-43, NODE-54 | PARITY-D04 |
| D05 | Brand design rules and voice guidance | confirmed | SRC-REFERENCES | PARITY | NODE-34, NODE-43 | PARITY-D05 |
| D06 | Multiple isolated Brand Kits per account | confirmed | SRC-REFERENCES | PARITY | NODE-16, NODE-43, NODE-58 | PARITY-D06 |
| D07 | Automatic on-brand generation across outputs | confirmed | SRC-REFERENCES, SRC-BRAND | PARITY | NODE-43, NODE-50 | PARITY-D07 |

The future D07 benchmark must score cross-format brand consistency, not just the existence of a Brand Kit screen.

---

# E. Production / Export

| ID | Public capability | Lovart evidence status | Sources | LUMI target | Owning Nodes | Acceptance |
|---|---|---|---|---|---|---|
| E01 | Image export PNG and JPEG | confirmed | SRC-EXPORT | PARITY | NODE-49, NODE-60 | PARITY-E01 |
| E02 | Video export MP4 | confirmed | SRC-EXPORT | PARITY | NODE-49, NODE-60 | PARITY-E02 |
| E03 | Slides export PDF/PPTX including editable text option | confirmed | SRC-EXPORT | PARITY | NODE-49, NODE-60 | PARITY-E03 |
| E04 | Layout export HTML | confirmed | SRC-EXPORT | PARITY | NODE-49, NODE-60 | PARITY-E04 |
| E05 | Vector object export SVG | confirmed | SRC-EXPORT | PARITY | NODE-49, NODE-60 | PARITY-E05 |
| E06 | Multi-object PSD export | confirmed | SRC-EXPORT | PARITY | NODE-49, NODE-60 | PARITY-E06 |
| E07 | Batch export of multiple selected assets | confirmed | SRC-EXPORT | PARITY | NODE-49, NODE-60 | PARITY-E07 |
| E08 | Print-oriented PDF with CMYK and bleed | confirmed_marketing | SRC-BRAND | PARITY | NODE-49, NODE-60 | PARITY-E08 |
| E09 | High-resolution upscale before export | confirmed | SRC-GETTING-STARTED | PARITY | NODE-45, NODE-49 | PARITY-E09 |

The core Export Formats docs explicitly define asset-type-dependent formats. CMYK/bleed is intentionally marked `confirmed_marketing` because the reviewed core export documentation is less explicit than the official tool page.

---

# F. Project / Collaboration

| ID | Public capability | Lovart evidence status | Sources | LUMI target | Owning Nodes | Acceptance |
|---|---|---|---|---|---|---|
| F01 | Project creation and persistent canvas | confirmed | SRC-GETTING-STARTED | PARITY | NODE-17, NODE-53, NODE-54 | PARITY-F01 |
| F02 | Reusable asset library across projects | confirmed | SRC-REFERENCES | PARITY | NODE-18, NODE-45, NODE-53 | PARITY-F02 |
| F03 | Project chat history and session revisit | confirmed | SRC-CHAT | PARITY | NODE-35, NODE-54, NODE-57 | PARITY-F03 |
| F04 | Version compare, restore and branch | confirmed_marketing | SRC-VERSION | SUPERSET | NODE-15, NODE-42, NODE-59 | Owning Node eval |
| F05 | Publish assets to Lovart community feed | confirmed | SRC-EXPORT | DEFER | NODE-61 | Deferred |
| F06 | Team review/comment via shared project/session | confirmed_marketing | SRC-TEAM | PARITY | NODE-61, NODE-62 | PARITY-F06 |
| F07 | Approval/flag review workflow | confirmed_marketing | SRC-TEAM | PARITY | NODE-62 | PARITY-F07 |

F06/F07 must be revalidated immediately before implementation because the current evidence is official blog/team-plan material rather than the highest-tier operational docs.

---

# G. Platform / SaaS

| ID | Public capability | Lovart evidence status | Sources | LUMI target | Owning Nodes | Acceptance |
|---|---|---|---|---|---|---|
| G01 | Credits consumed by Agent/model/task complexity | confirmed | SRC-PRICING | PARITY | NODE-27, NODE-63 | PARITY-G01 |
| G02 | Subscription plans and credit top-ups | confirmed | SRC-PRICING | PARITY | NODE-63 | PARITY-G02 |
| G03 | Credit expiry/reset rules | confirmed | SRC-PRICING | PARITY | NODE-27, NODE-63 | PARITY-G03 |
| G04 | Commercial-use rights subject to underlying model license/TOS | confirmed | SRC-PRICING | SUPERSET | NODE-15, NODE-65 | Owning Node eval |
| G05 | Plan-dependent Brand Kit quotas | confirmed | SRC-REFERENCES | PARITY | NODE-16, NODE-63 | PARITY-G05 |
| G06 | External agent integration via Lovart/OpenClaw skill | confirmed | SRC-CHAT | DEFER | NODE-25, NODE-26 | Deferred |
| G07 | Artifact-level provenance, rights metadata and audit lineage | not_confirmed | — | SUPERSET | NODE-15, NODE-65 | Owning Node eval |
| G08 | Durable workflow recovery / resumable agent execution | not_confirmed | — | SUPERSET | NODE-20, NODE-28, NODE-68 | Owning Node eval |

G07/G08 are deliberate LUMI product requirements. `not_confirmed` only records absence of qualifying evidence in the reviewed public Lovart source set.

---

## 4. High-priority gap clusters

The 67 rows map into implementation clusters rather than independent feature tickets:

| Gap cluster | Capability IDs | Primary Nodes | Product risk if missing |
|---|---|---|---|
| Agent control + model routing | A01-A09, C09-C10 | NODE-22..24, NODE-28..37, NODE-54 | Product behaves like a single chat wrapper rather than an autonomous design system |
| Editable Canvas + local editing | B01-B14 | NODE-38..42, NODE-45, NODE-47, NODE-55..59 | Outputs remain flat images and cannot support precise iterative design |
| Multi-modal generation | C01-C08 | NODE-22..24, NODE-46..49 | Cannot deliver image/video/variant production workflows |
| Brand memory + consistency | D01-D07 | NODE-34..36, NODE-43, NODE-50, NODE-58 | Cannot scale a coherent brand across many assets |
| Production export | E01-E09 | NODE-45, NODE-49, NODE-60 | Product stops at preview instead of usable deliverables |
| Project/review workflow | F01-F07 | NODE-17, NODE-18, NODE-35, NODE-53..54, NODE-61..62 | No durable project collaboration or approval lifecycle |
| SaaS economics/governance | G01-G08 | NODE-15..16, NODE-20, NODE-27, NODE-63, NODE-65, NODE-68 | Costs, rights, quotas and recovery are not production-safe |

## 5. LUMI SUPERSET thesis

The current seven SUPERSET targets are intentional architecture advantages rather than speculative UI features:

1. **A10 Skill Registry** — versioned skill definition, dependencies, permissions and eval profile.
2. **B06 Artifact history** — move from UI history to immutable object/version lineage.
3. **B12 Non-destructive editing** — deterministic branch/restore/provenance rather than opaque variations.
4. **F04 Version control** — version-bound compare/fork/restore across artifacts and project state.
5. **G04 Rights governance** — provenance-aware rights metadata instead of a blanket export claim.
6. **G07 Provenance/audit lineage** — trace every artifact derivation, provider, prompt and edit operation.
7. **G08 Durable recovery** — resumable workflows, idempotent side effects, checkpoints and DR evidence.

## 6. Acceptance mapping contract

Every `PARITY` row is linked one-to-one with a future case under `evals/datasets/product-parity/v1/`. NODE-06 cases are intentionally marked `SPECIFIED_NOT_RUN`: the owning implementation Nodes must provide fixtures, executable runners/graders, and baseline/candidate evidence before a capability can be marked complete.

High-signal examples already specified:

- `PARITY-B10`: change only a poster background while product identity, logo, QR position and QR size remain unchanged.
- `PARITY-D07`: generate 1:1, 9:16 and 16:9 assets from one Brand Kit and verify color/font/logo/style consistency.
- `PARITY-A02`: research before design, record sources, then ground design direction in that research.
- `PARITY-A08`: route image generation, local edit and video tasks through capability-aware model policies.
- `PARITY-G01`: record task usage/cost and enforce a budget.
- `PARITY-F07`: bind review/approval state to a concrete artifact version and audit event.

## 7. CI contract

Run:

```bash
make product-parity-validate
```

The validator fails if any of these drift:

```text
7 category coverage
67 capability total
56 PARITY / 7 SUPERSET / 4 DEFER
56 confirmed / 9 confirmed_marketing / 2 not_confirmed
official Lovart source IDs and URLs
Owning NODE syntax
PARITY -> acceptance case one-to-one mapping
56 product-parity acceptance specs
matrix/dataset version and observation date consistency
```

The same validator is invoked from `scripts/ci-contracts`, so GitHub `contracts` becomes the blocking repository gate for the matrix.

## 8. Refresh policy

Competitor behavior changes. Before a Node implements a capability whose evidence is older than 90 days—or whenever a Lovart release materially changes the capability—the owner must:

```text
re-check official sources
→ update evidence catalog / observed_at
→ bump matrix version if semantics changed
→ update capability row
→ update acceptance case if necessary
→ run product-parity-validate
```

Do not silently rewrite historical benchmark semantics under the same matrix version.

## 9. Current conclusion

NODE-06 establishes **what LUMI must be able to prove**, not that those 56 parity capabilities already exist. The next benchmark node, NODE-07, should take the model-related capability cluster and determine which current providers/models meet LUMI's quality, latency, cost, control and commercial constraints.
