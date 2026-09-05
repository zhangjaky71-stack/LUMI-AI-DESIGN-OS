# Image Edit Runtime V1

## Purpose

NODE-47 implements structural-first and protected pixel-local image editing. The target golden scenario is: **keep product, logo and QR unchanged; change only the requested background**.

## Frozen execution order

```text
Edit intent
→ Edit Planner
→ STRUCTURAL_IR_EDIT when DesignOperation can express the change
  → NODE-38/NODE-39 guarded operation
  → new DesignDocumentVersion
  → no model cost
OR
→ Pixel edit
  → source/version/rights pin
  → mask source/version/checksum/dimensions pin
  → hard protected-mask overlap preflight
  → NODE-22 image.mask_edit/image.edit
  → durable output
  → resolution + protected-region + Identity + QR + OCR + intended-change postflight
  → optional protected-source compositing fallback
  → full postflight rerun
  → NODE-42 append-only ArtifactVersion
  → PASS-only branch head CAS
  → optional Design IR REPLACE_ASSET
```

## Structural-first

Structural actions include move/resize text, set text, color/font changes, replace existing image asset, reorder/reparent layers and vector background color. These emit the frozen NODE-38 DesignOperation types and never invoke a provider.

## Mask coordinate contract

Every provider mask is pinned to:

- source asset id/version;
- source checksum;
- source width/height;
- editable rect in **source raster pixel space**;
- mask checksum/version/durable ref;
- origin (`USER_BRUSH`, `DESIGN_IR`, `DETECTOR`, `AGENT_PROPOSED`).

A source version, checksum or dimension change invalidates the old mask. High-impact generated masks require preview approval before construction.

## Protected content

Protected regions are explicit PRODUCT / LOGO / QR / LOCKED_TEXT / CONTENT records. A HARD protected region may not overlap the editable mask. Prompt text is not treated as enforcement evidence.

Postflight delegates remain owned by existing engines:

- NODE-39 ProtectedRegionEvaluator / QR / resolution constraints;
- NODE-44 Identity Engine;
- OCR adapter for locked text/wordmark;
- intended-change validator for the editable region.

Missing required validators fail closed.

## Provider routing

Local masked edits require `image.mask_edit`. Full edits require `image.edit`. If protected or identity requirements exist, the request additionally requires `image.reference_consistency`. NODE-22 ModelRouter now honors `constraints.required_capabilities` before invocation, so a provider lacking any required capability is rejected before paid execution.

## Fallback

Transport/rate-limit/provider failures use existing NODE-22 safe retry/fallback semantics. A successful provider response that later fails protected-region postflight is **not** blindly retried as if delivery failed. For local/hybrid edits, NODE-47 may composite source protected regions over the generated candidate and then rerun the full postflight. If it still fails, the candidate is REJECTED and the source remains unchanged.

A broader edit requiring removal of hard protection needs explicit user confirmation or a new spec; the system never silently relaxes the lock.

## Artifact/version semantics

Source version `v3` is immutable. Pixel edit creates a new candidate version. `ArtifactHistoryImageEditAdapter` adds the candidate with `advance_branch_head=False` and creates `EDITED_FROM v3→v4` lineage.

- PASS → candidate becomes READY, then branch head CAS advances from source to candidate.
- REPAIR → candidate stays DRAFT and branch head remains source.
- REJECT → candidate becomes REJECTED and branch head remains source.

Stale source branch head rejects the edit commit rather than overwriting concurrent work.

## Canvas bridge

After a pixel candidate passes and becomes READY, an edit associated with a Design IR image node emits `REPLACE_ASSET` using the new durable asset ref. This guarded operation creates a new DesignDocumentVersion; version conflict is preferable to overwriting a newer canvas state.

## Provenance

The edit-specific provenance binds source artifact/asset version and checksum, instruction hash, mask hash, protected-region hash, full constraint snapshot hash, validation report hash/decision, provider/model/request id, routing reasons, price snapshot/cost confidence, seed, git SHA and Identity validation snapshot.

No face embedding or raw biometric feature is stored.

## Golden suite

`fixtures/image-edit/node-47-golden.json` deterministically materializes 125 synthetic contract cases across:

A. unchanged product;
B. unchanged logo;
C. unchanged/decodable QR;
D. requested background changed;
E. title resize structural with zero model calls.

This suite is not live-provider visual-quality evidence. Production routing still requires approved provider/model edit benchmarks for protected-region similarity, QR/OCR fidelity, intended-region success, latency and cost.

## Completion rule

NODE-47 remains `IMPLEMENTED / VALIDATING / not COMPLETE` until hosted contract/quality/integration/benchmark gates actually run green **and** at least one production edit route has approved live benchmark evidence for the golden protected-edit scenarios.
