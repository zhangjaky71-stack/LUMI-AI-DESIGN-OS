# NODE-47 — Image Edit & Local Edit Pipeline

> Phase: 6 Generation & Quality  
> Status: **IMPLEMENTED / VALIDATING / not COMPLETE**  
> Priority: P0 / LOVART-PARITY CORE  
> Depends on: NODE-39, NODE-42, NODE-44, NODE-46  
> Produces: structural-first edit planning, pixel mask editing, protected-content validation, append-only Artifact/Canvas lineage

## Implemented boundary

NODE-47 implements the golden requirement “only change the requested region; keep protected product/logo/QR/text unchanged.” Structural Design IR mutations always take priority. Generative editing is invoked only when pixel content must change.

Primary evidence:

- `services/image-edit/src/lumi_image_edit/model.py`
- `services/image-edit/src/lumi_image_edit/planner.py`
- `services/image-edit/src/lumi_image_edit/mask.py`
- `services/image-edit/src/lumi_image_edit/pipeline.py`
- `services/image-edit/src/lumi_image_edit/model_gateway_adapter.py`
- `services/image-edit/src/lumi_image_edit/validation.py`
- `services/image-edit/src/lumi_image_edit/artifact_adapter.py`
- `services/image-edit/src/lumi_image_edit/structural_adapter.py`
- `services/image-edit/tests/test_image_edit.py`
- `db/migrations/0006_image_edit.sql`
- `fixtures/image-edit/node-47-golden.json`
- `scripts/validate_image_edit.py`
- `scripts/benchmark_image_edit.py`
- `docs/runtime/IMAGE-EDIT-V1.md`
- `.github/workflows/image-edit.yml`

## Structural first

When the edit can be expressed with the frozen NODE-38 operation set (`SET_PROPERTY`, `MOVE_NODE`, `RESIZE_NODE`, `REORDER_NODE`, `REPARENT_NODE`, `REPLACE_ASSET`, `SET_TEXT`, `APPLY_STYLE`), the planner returns `STRUCTURAL_IR_EDIT` and no provider call/cost is permitted.

## Pixel editing

Pixel-local edit specs pin source artifact/asset version, source checksum/dimensions, mask version/hash/pixel coordinates, protected regions, identity requirements and active constraint/brand versions. Old masks cannot be reused against a changed source.

## Provider capability gate

Masked edits require `image.mask_edit`; full pixel edits require `image.edit`. Protected/identity edits additionally require `image.reference_consistency`. NODE-22 routing rejects candidates missing any additional required capability before paid invocation.

## Postflight

The pipeline requires actual postflight evidence, not prompt promises: protected-region visual comparison, Identity, QR decode, locked-text OCR, resolution and intended-region change. Missing required validators fail closed.

## Fallback and version safety

Protected-region failure on a local/hybrid edit may use source-region compositing and rerun the complete postflight once. A candidate never overwrites the source. PASS becomes a new READY ArtifactVersion and advances the branch with CAS; REPAIR remains DRAFT; REJECT remains rejected/off-head.

After pixel PASS, an associated Canvas image node is updated via guarded `REPLACE_ASSET`, producing a new DesignDocumentVersion.

## Golden suite

125 deterministic synthetic contract cases cover product/logo/QR preservation, requested background change and zero-model structural title resize. These cases do not claim live provider visual quality.

## Definition of Done

```text
local edit pipeline implemented
+ hosted golden/contract/integration gates green
+ approved live provider protected-edit benchmark evidence
```

Until both hosted CI and live provider benchmark evidence exist, NODE-47 remains **IMPLEMENTED / VALIDATING / not COMPLETE**.

下一节点：NODE-48 Video Generation。
