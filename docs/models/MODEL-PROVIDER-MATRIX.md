# LUMI AI Design OS — Model Provider Matrix v1.0.0

> Observed at: **2026-08-13**  
> Pricing snapshot expires: **2026-09-12**  
> NODE: **NODE-07 — Model Provider Matrix**  
> Registry manifest: `docs/models/provider-matrix-manifest.json`  
> First-party source catalog: `docs/models/provider-sources.json`  
> Machine-readable provider records: `docs/models/providers/*.json`  
> Candidate routes: `docs/models/route-candidates.json`  
> Live benchmark spec: `evals/datasets/model-provider/suite.json`

---

## 1. Decision rule

NODE-07 does **not** declare a single “best model”. It establishes the factual candidate set and the evaluation contract that later Model Gateway work will consume.

The routing rule is:

```text
provider documentation
→ normalize capability + lifecycle + price
→ form task-specific candidate set
→ run LUMI Benchmark Harness with real provider access
→ compare quality / constraints / latency / cost / failures
→ select or change TaskPolicy primary + fallback
```

Until live benchmark evidence exists:

```text
selected_primary = null
quality          = NOT_MEASURED
latency_ms       = NOT_MEASURED
benchmark_status = NOT_MEASURED
```

Provider marketing labels such as “fastest”, “frontier”, or “studio quality” are recorded only as documented positioning. They never become fabricated LUMI scores.

## 2. Snapshot

| Dimension | v1.0.0 |
|---|---:|
| Providers | 5 |
| Model records | 28 |
| Route-eligible models | 27 |
| Stable | 23 |
| Preview | 4 |
| Deprecated | 1 |
| First-party evidence records | 30 |
| Task routes | 15 |
| Live-measured models | 0 |

Providers:

- OpenAI
- Google Gemini API
- Anthropic Claude API
- Black Forest Labs
- Runway API

The registry includes reasoning/vision, image generation/editing, video generation/editing, and text/multimodal embeddings. OCR-like extraction and rerank are initially represented as replaceable multimodal/structured reasoning routes rather than creating irreversible dependency on a dedicated vendor before benchmark evidence exists.

---

# 3. Reasoning / multimodal candidates

| Registry ID | Lifecycle | Context | Documented role in LUMI candidate set | Price snapshot | Benchmark |
|---|---|---:|---|---|---|
| `openai:gpt-5.6-sol` | stable | 1.05M | frontier / Director / design judgment | $5 input, $30 output / MTok | NOT_MEASURED |
| `openai:gpt-5.6-terra` | stable | 1.05M | balanced default | $2.50 / $15 | NOT_MEASURED |
| `openai:gpt-5.6-luna` | stable | 1.05M | fast / high volume | $1 / $6 | NOT_MEASURED |
| `google:gemini-3.6-flash` | stable | 1.048M | default / fast multimodal | $1.50 / $7.50 | NOT_MEASURED |
| `google:gemini-3.5-flash-lite` | stable | 1.048M | cost/high-volume | $0.30 / $2.50 | NOT_MEASURED |
| `google:gemini-3.1-pro-preview` | preview | 1.048M | frontier multimodal | tiered by context length | NOT_MEASURED |
| `anthropic:claude-fable-5` | stable | 1M | frontier / long-horizon Director | $10 / $50 | NOT_MEASURED |
| `anthropic:claude-opus-5` | stable | 1M | complex agentic / design judgment | $5 / $25 | NOT_MEASURED |
| `anthropic:claude-sonnet-5` | stable | 1M | balanced default | standard $3 / $15; temporary introductory price is separately recorded | NOT_MEASURED |
| `anthropic:claude-haiku-4.5` | stable | 200K | fast/high-volume | $1 / $5 | NOT_MEASURED |

Prices above are provider-documented snapshots and are not a promise of future price. The machine-readable records preserve special pricing rules, including context-tier multipliers and temporary promotions.

### Candidate routes

```text
reasoning.director
  openai:gpt-5.6-sol
  anthropic:claude-fable-5
  anthropic:claude-opus-5
  google:gemini-3.1-pro-preview

reasoning.default
  openai:gpt-5.6-terra
  anthropic:claude-sonnet-5
  google:gemini-3.6-flash

reasoning.fast
  openai:gpt-5.6-luna
  anthropic:claude-haiku-4.5
  google:gemini-3.5-flash-lite
```

The preview Gemini candidate can participate in comparison but cannot become a preview-only production route with no stable fallback.

---

# 4. Image generation / edit candidates

| Registry ID | Lifecycle | Key documented capability | Cost basis | Benchmark |
|---|---|---|---|---|
| `openai:gpt-image-2` | stable | generation + editing + high-fidelity image input | input/output image token pricing | NOT_MEASURED |
| `google:gemini-3.1-flash-image` | stable | Nano Banana 2; generation/edit; up to 4K | $60 / MTok image output plus input/text output | NOT_MEASURED |
| `google:gemini-3.1-flash-lite-image` | stable | high-volume generation/edit; up to 1K | $30 / MTok image output plus input/text output | NOT_MEASURED |
| `google:gemini-3-pro-image` | stable | Nano Banana Pro; 4K/layout/text-focused candidate | $120 / MTok image output plus input/text output | NOT_MEASURED |
| `black-forest-labs:flux-2-max` | stable | premium generation/edit, up to 8 API refs, exact color/typography | from $0.07/MP | NOT_MEASURED |
| `black-forest-labs:flux-2-pro` | stable | pinned production snapshot, multi-ref generation/edit | generation from $0.03/MP; edit from $0.045/MP | NOT_MEASURED |
| `black-forest-labs:flux-2-flex` | stable | fine control / typography | $0.06/MP | NOT_MEASURED |
| `black-forest-labs:flux-2-klein-4b` | stable | high-volume variant candidate | from $0.014/image | NOT_MEASURED |

### Required image benchmark routes

`image.general` compares general prompt adherence and commercial-quality output. `image.hero` emphasizes premium final assets. `image.text_heavy` emphasizes multilingual typography/layout. `image.local_edit` gives dominant weight to protected-content constraints. `image.fast_variants` emphasizes cost/throughput without allowing identity/constraint collapse.

The most important editing benchmark is the NODE-06 parity scenario:

```text
change background only
product identity unchanged
logo unchanged
QR geometry unchanged
```

A model that looks aesthetically better but violates protected regions must lose the precision-edit route.

---

# 5. Video generation / edit candidates

| Registry ID | Lifecycle | Documented mode | Cost basis | Benchmark |
|---|---|---|---|---|
| `google:gemini-omni-flash-preview` | preview | conversational generation/edit, 3–10s 720p | effective provider price approx. $0.10/s at 720p | NOT_MEASURED |
| `google:veo-3.1-generate-preview` | preview | cinematic text/image, first/last frame, references, extension, up to 4K | $0.40/s 720/1080; $0.60/s 4K | NOT_MEASURED |
| `google:veo-3.1-lite-generate-preview` | preview | lower-cost 720/1080 generation | $0.05/s 720; $0.08/s 1080 | NOT_MEASURED |
| `runway:gen4.5` | stable | text/image to video | $0.12/s | NOT_MEASURED |
| `runway:gen4_turbo` | stable | image to video | $0.05/s | NOT_MEASURED |
| `runway:aleph2` | stable | video transformation/edit | $0.28/s, minimum generation charge recorded | NOT_MEASURED |

LUMI deliberately keeps stable Runway fallbacks on video routes where Google candidates are preview. Provider recommendation does not override lifecycle risk.

---

# 6. Embedding candidates

| Registry ID | Input | Price snapshot | Intended comparison |
|---|---|---|---|
| `openai:text-embedding-3-large` | text | $0.13/MTok | text retrieval quality |
| `openai:text-embedding-3-small` | text | $0.02/MTok | low-cost text retrieval |
| `google:gemini-embedding-2` | text/image/video/audio/PDF | modality-specific prices | unified cross-modal asset retrieval |

`embedding.multimodal` currently has only one first-party candidate in this five-provider registry. That is a registry fact, not permission to skip later retrieval benchmarking or add no fallback strategy.

---

# 7. Lifecycle policy

Lifecycle is an explicit routing input:

```text
stable      → eligible for primary/fallback after benchmark
preview     → eligible for benchmark; production use requires fallback/risk policy
deprecated  → not route eligible
legacy      → not route eligible
shutdown    → not route eligible
```

The registry carries `openai:sora-2-legacy` as a deprecated sentinel specifically to prove that stale models cannot accidentally enter an active route.

Provider lifecycle must be revalidated before release when a source or price snapshot becomes stale.

---

# 8. Pricing policy

All pricing records include:

```text
provider-native metric
USD normalization where documented
source ID
observed_at
pricing_expires_at
```

Pricing snapshot v1 expires within 30 days. NODE-22/23/27 must never hard-code the prices in application logic; the normalized Capability Registry / Cost Ledger owns live price policy.

Special cases that must remain machine-readable instead of flattened:

- context-length pricing tiers;
- cached input pricing;
- temporary promotional prices;
- per-megapixel image costs;
- image token output costs;
- per-second video costs;
- minimum generation charges;
- multimodal embedding modality costs.

---

# 9. Provider Adapter contract for NODE-22

Every provider adapter must expose the same conceptual stages:

```text
resolve capability route
→ validate lifecycle + provider health
→ normalize LUMI request
→ estimate worst-case cost
→ enforce budget/quota
→ invoke provider
→ normalize result
→ capture provider request/task id
→ capture usage and actual cost
→ store artifact/provenance metadata
→ classify provider error/refusal
```

Agent code must not construct provider-native payloads directly.

Minimum normalized error taxonomy remains:

```text
AUTH_ERROR
RATE_LIMIT
TIMEOUT
PROVIDER_5XX
CONTENT_BLOCKED
REFUSAL
INVALID_REQUEST
CAPABILITY_UNAVAILABLE
INSUFFICIENT_QUOTA
UNKNOWN
```

Anthropic's documented refusal stop reason, async Runway task semantics, signed BFL output URLs, and provider-specific preview/deprecation states are examples of details that adapters normalize instead of leaking into Agent business logic.

---

# 10. Live benchmark contract

The benchmark suite is `evals/datasets/model-provider/suite.json` and maps all 15 routes to task groups.

Core dimensions:

```text
task_success
constraint_success
quality
latency_ms
cost_usd
failure_rate
```

Profiles include:

- Director planning, constraint extraction, tool selection and repair decisions;
- multimodal text/layout extraction;
- retrieval rerank;
- image general/hero/typography/local edit/fast variants;
- video general/fast/edit;
- text and multimodal embedding retrieval.

Without provider keys and a positive explicit budget, the live suite is **SKIPPED**, never PASS. NODE-07 records candidates and benchmark design; it does not fabricate measured results.

---

# 11. Route selection policy

Current route policy is deliberately:

```text
CANDIDATE_SET_ONLY_UNTIL_LIVE_BENCHMARK
```

Every `selected_primary` is `null`.

Later routing should be task-policy-specific. Example:

```text
image.local_edit.precision
  constraint_success  35%
  quality             45%
  latency             10%
  cost                10%
```

A different high-volume route can weight cost/latency more heavily. There is no globally optimal model.

---

# 12. Registry validation

Run:

```bash
make model-provider-validate
```

`script/validate_model_provider_matrix.py` / `scripts/validate_model_provider_matrix.py` enforces:

- five required providers;
- first-party source domains only;
- observation and price-expiry consistency;
- 28 unique model records / 27 active candidates;
- required modality coverage;
- active candidate pricing presence;
- deprecated/legacy/shutdown models excluded from routing;
- unmeasured quality/latency remain exactly `NOT_MEASURED`;
- every route references valid eligible candidates;
- preview-only candidate sets require stable fallback;
- no primary model may be selected before benchmark;
- every route maps to a benchmark group;
- missing live credentials remain a SKIPPED condition by contract.

The same validator is wired into the blocking GitHub `contracts` job and a Python regression test.

---

# 13. Refresh policy

Before relying on a snapshot older than 30 days:

```text
re-read first-party model + pricing + lifecycle docs
→ update provider source catalog
→ update model records
→ bump registry version if semantics changed
→ re-run contract validation
→ re-run affected live benchmark routes
→ only then change routing policy
```

A provider adding a newer model is not itself sufficient reason to migrate. Migration must pass the LUMI task benchmark and release gate.

## 14. Current conclusion

NODE-07 v1.0.0 establishes a current, provider-neutral **candidate and benchmark contract**. It intentionally stops one step before model winner selection because no commercial live benchmark credentials/budget have been executed in this Node.

The next engineering node, NODE-08, can now test Canvas technology against known product requirements while NODE-22/23 later consume this registry to build the actual Model Gateway and Capability Registry.
