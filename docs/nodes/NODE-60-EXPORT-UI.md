# NODE-60 — Export Product UX

> Phase: 7 Frontend Product  
> Status: **IMPLEMENTED / VALIDATING / NOT COMPLETE**  
> Priority: P0  
> Depends on: NODE-49, NODE-59  
> Produces: 格式/尺寸/批量导出设置、Job进度、下载/Manifest UI

---

## 1. 目标

让用户从 Exact Version 选择真实支持的导出设置，并清楚了解哪些是直接缩放、哪些需要重新设计适配，最后获得可靠下载包。

## 2. Export Entry

来源支持 selected Frame、selected ArtifactVersion、Project deliverables 和 batch Frames。UI 默认锁定并显示 exact `ArtifactVersion` + exact `DesignVersion`；`latest/head/current` fail closed。

## 3. Format Options

能力来自 NODE-49 verified V1：PNG、JPEG、WebP、SVG、PDF、Project Package、ZIP Batch，并按内容能力进一步过滤。SVG 仅 vector-capable source 显示；batch 仅显示 multi-frame verified formats。

CMYK、Display P3、PSD、bleed、crop marks 继续隐藏，直到后端存在独立验证实现。

## 4. Size / Adaptation

实现 original、2×、custom dimensions 和 social presets。若 aspect ratio 改变，UI 明确分成：

```text
SCALE / CROP (NODE-49 export geometry)
versus
Adapt design with AI -> create a NEW DesignVersion first -> export that exact version
```

不会把 `DESIGN_ADAPTATION` 偷塞进 ExportSpec。

## 5. Quality / Alpha / Print

只在格式真实支持时显示 quality/alpha；JPEG 不出现透明导出。V1 未验证 print capabilities 不显示。

## 6. Estimate

Export render 显示“无 AI generation charge”。AI Adapt 属于独立版本生成 workflow，费用估算必须在该 workflow 创建任务前完成。

## 7. Job Progress

UI 读取真实 NODE-49 状态：PENDING / RENDERING / PACKAGING / VALIDATING / READY / FAILED / EXPIRED。不会制造 99% 进度；只展示服务返回的 progress。

## 8. Download

READY 才能取得下载。每次下载通过服务刷新短期 signed URL；过期只重新签名，不 rerender。signed URL 只存在 ephemeral UI state，不进入 canonical history。

## 9. Manifest / History

History 保留 exact source IDs、files、checksum、size 和 manifest availability。普通用户看到安全 provenance summary；原始 worker payload/secret/system prompt 不进入 UI。

## 10. Failure / Partial Retry

错误使用 safe allowlist。NODE-49 V1 当前只有 job-level `error_code`，没有 durable failed-item identity 和 per-file retry command。因此 NODE-60 **不伪造 partial retry**；该项保持 integration dependency，直到 NODE-49 contract 增补并完成测试。

## 11. Validation

- `scripts/validate_export_ui.py`
- `apps/web/src/lib/export-ui/*.test.ts`
- `apps/web/e2e/export-ui.spec.ts`
- `.github/workflows/export-ui.yml`
- NODE-49 engine + NODE-59..54 regression chain

## 12. Definition of Done

```text
export UX static/unit/E2E green
+ exact-version/capability/download scenarios green
+ backend partial retry contract green
+ hosted pinned gates green
```

Next: **NODE-61 — Collaboration**.
