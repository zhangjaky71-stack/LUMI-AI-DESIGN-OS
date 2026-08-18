# NODE-60 — Export Product UX

> Phase: 7 Frontend Product  
> Status: **CORE IMPLEMENTED / VALIDATING / NOT COMPLETE**  
> Priority: P0  
> Depends on: NODE-49, NODE-59  
> Produces: Exact-version export capability、batch package、job progress、signed download、Manifest UI

---

## 0. Implementation snapshot — 2026-08-18

Implemented on `feat/node-60-export-ui`:

- Product API is composed over NODE-49 Export Engine; no second export renderer/job store is introduced.
- Export entry is locked to exact `ArtifactVersion` IDs from the currently viewed historical version and current Run artifacts.
- Capability is evaluated independently for every exact version by `snapshot_exact` + export authorization.
- Current runtime formats are the actual NODE-49 enum only: `ORIGINAL / PNG / JPEG / MP4 / PDF / PPTX`.
- Current verified renderer is same-format copy-through; capability therefore exposes ORIGINAL plus the one matching target format when source MIME matches a renderer target.
- WebP/SVG are not exposed because the runtime has no such ExportFormat/render capability.
- Resize, quality, alpha, crop, social presets, AI Adapt and print/CMYK/bleed controls remain hidden because the runtime request contract does not support them.
- Export Job creation requires a real Project Core `export` Task and verifies that the Task belongs to the selected Project.
- Idempotency-Key is a UUID operation identity and is persisted by NODE-49.
- Batch exact versions are packaged with `force_zip`; single-item export preserves the individual package.
- Product Job/read/cancel/download routes are tenant scoped.
- Product responses omit internal bucket/storage keys.
- Job UI follows the actual runtime enum: `PLANNED → QUEUED → RENDERING → PACKAGING → READY`, with `FAILED / CANCELLED / EXPIRED` terminal states.
- READY download requests issue a new signed URL each time through `issue_download`; the existing READY package is reused and not re-rendered.
- Package UI exposes filename, size, checksum and archive state.
- Manifest UI exposes exact source ArtifactVersion IDs, checksum, renderer version, operation ID and exporter version.
- Current local copy-through path is labeled “No AI generation fee”; storage/egress and future renderer cost are not guessed.
- Current NODE-49 failure model is whole-job, so the UI explicitly does not offer fake per-item partial retry.
- Workspace Inspector hosts Export directly under the selected exact version, so opening historical v3 exports v3 even when branch HEAD is later.

NODE-60 remains **NOT COMPLETE** because the current renderer does not provide transcoding/resize/quality/alpha/WebP/SVG/Print/AI Adapt, cost estimation is incomplete, per-item partial retry is not modeled, export jobs cannot yet be listed/reopened after page refresh without a known job ID, production ExportEngine composition is not proven, and browser/PostgreSQL/worker E2E plus hosted executed-green CI remain open.

## 1. 目标

让用户从 exact ArtifactVersion 选择**实际 renderer 可证明**的导出能力，创建可追踪 ExportJob，获得 Manifest 与可刷新签名的下载包。Export UI 不得把产品愿景当成 runtime capability。

## 2. Export Entry

当前 core 来源：

- 当前 Canvas/Versions 面板正在查看的 exact ArtifactVersion；
- 当前 Run 已产生的其他 exact ArtifactVersions；
- batch exact versions。

不自动 resolve `latest` 或 branch HEAD。

Project deliverable 全量选择器仍是后续 gap。

## 3. Format Options

当前 runtime enum：

```text
ORIGINAL
PNG
JPEG
MP4
PDF
PPTX
```

当前 `VerifiedSameFormatRenderer` 不做转码；例如 PNG 源只显示 ORIGINAL + PNG。WebP/SVG 不在 runtime enum，因此不显示。

## 4. Size / Adaptation

当前 `ExportRequestItem` 只有：

```text
artifact_version_id
target_format
output_name
```

所以以下均不得显示为可用功能：

```text
2x / scale
custom dimensions
social presets
crop
AI Adapt
```

AI Adapt 未来必须先创建新的 DesignVersion，再 export；不能在 ExportJob 内偷偷改变设计。

## 5. Quality / Alpha

当前 runtime request 没有 quality/alpha 参数，因此隐藏。

## 6. Print

当前 NODE-49 没有 DPI/bleed/CMYK/crop-mark contract 或验证路径，因此隐藏。

## 7. Estimate

当前 verified copy-through 可明确显示：

```text
No AI generation fee
```

但 storage/egress、未来 transcoder、AI Adapt 的真实金额尚无统一 estimate contract，保持 gap。

## 8. Job Progress

真实 runtime 状态：

```text
PLANNED
QUEUED
RENDERING
PACKAGING
READY
FAILED
CANCELLED
EXPIRED
```

UI 不使用文档中不存在于代码的 `VALIDATING` 状态。

当前页面内会轮询已知 job ID；Project activity / list-reopen-after-refresh 仍未闭合。

## 9. Download

- READY package通过 signed grant 下载；
-每次 Download 都重新 `issue_download`；
- signed URL过期不会重新render；
- URL不写入 ExportJob；
-产品响应显示filename/file size/checksum；
-内部 bucket/storage key不下发。

## 10. Manifest

Manifest UI显示：

```text
operation id
exporter version
exact artifact version id
filename/mime/size/checksum
renderer version
```

这证明输出可追溯到 exact source version。

## 11. Failure

当前 NODE-49 在任一 render/packaging exception 时将整个 job标为 `FAILED`，虽可能持有已完成outputs，但没有per-item retry state machine。因此本节点不能声称partial retry已完成。

## 12. Tests

Core test surface覆盖：

- exact version capability；
- PNG只暴露ORIGINAL + PNG；
-未知 MIME只暴露ORIGINAL；
-未实现请求参数不进入product schema；
- product response不泄露storage key；
-真实ExportJobStatus enum；
- WebP/SVG parser rejection；
- Manifest exact version/checksum；
-现有NODE-49 exact snapshot/idempotency/download/renderer tests回归。

## 13. 验收标准

- [x] 用户只能选择当前 runtime 真实支持格式。
- [x] Export始终绑定 exact ArtifactVersion。
- [x] Batch exact versions可创建ZIP package。
- [x] Job进度映射真实runtime状态。
- [x] 下载签名可刷新而不重render。
- [x] Exact Version / Manifest可追溯。
- [x] 未支持Print/AI Adapt/resize等能力不显示假控件。
- [ ] Crop/resize与AI Adapt真实能力及新DesignVersion流程。
- [ ] WebP/SVG/跨格式transcoding。
- [ ] Print DPI/CMYK/bleed/crop marks。
- [ ] 完整 cost estimate。
- [ ] Per-item batch failure/retry。
- [ ] ExportJob list/reopen/resume after refresh。
- [ ] Production ExportEngine factory composition proof。
- [ ] Browser/PostgreSQL/worker E2E + Hosted executed-green CI。

## 14. Definition of Done

```text
exact export E2E green
+ capability/transcode/print/adapt contracts green
+ batch/retry/reopen scenarios green
+ signed download/manifest green
+ hosted CI executed green
```

当前未满足完整 Definition of Done，因此保持 **NOT COMPLETE**。

完成 Phase 7 core slice，下一节点：NODE-61 Collaboration。
