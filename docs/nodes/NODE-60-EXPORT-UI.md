# NODE-60 — Export Product UX

> Phase: 7 Frontend Product  
> Status: SPECIFIED / READY FOR IMPLEMENTATION  
> Priority: P0  
> Depends on: NODE-49, NODE-59  
> Produces: 格式/尺寸/批量导出设置、Job进度、下载/Manifest UI

---

## 1. 目标

让用户从Exact Version选择真实支持的导出设置，并清楚了解哪些是直接缩放、哪些需要重新设计适配，最后获得可靠下载包。

## 2. Export Entry

来源：

- selected Frame；
- selected ArtifactVersion；
- Project deliverables；
- batch Frames。

默认锁定exact version并显示。

## 3. Format Options

根据内容能力动态显示：

```text
PNG
JPEG
WebP
SVG if structurally supported
PDF
Project Package
ZIP Batch
```

不支持的格式不显示“假按钮”。

## 4. Size

```text
original
2x/scale
custom dimensions
preset social sizes
```

若aspect ratio改变：提示：

```text
Crop/scale
or
Adapt design with AI
```

后者先创建新DesignVersion，再export。

## 5. Quality / Alpha

只展示provider/renderer真实支持参数。JPEG不显示透明背景；PNG/WebP按能力。

## 6. Print

只有 NODE-49 已验证的print功能才显示DPI/bleed/CMYK等，不能营销先行。

## 7. Estimate

批量/AI adaptation可能产生费用，创建任务前显示估算。纯本地render可以显示“无AI生成费用”。

## 8. Job Progress

状态：

```text
Preparing
Rendering 3/8
Packaging
Validating
Ready
```

支持离开页面后通过通知/Project activity再次打开。

## 9. Download

- signed URL；
- filename安全；
-过期后刷新签名，不重新生成；
-下载项显示file size/checksum可选。

## 10. Manifest

高级/企业用户可下载provenance manifest；普通用户可展开查看“使用了哪些来源/模型”的摘要。

## 11. Failure

具体到Frame/file：字体缺失、渲染失败、权限变化、storage error。Batch允许在policy定义下重试失败项而非全部重做。

## 12. Tests

- exact version；
- format capability；
- aspect ratio adaptation；
- batch partial fail；
- expired download URL refresh；
- print options hidden whenunsupported；
- cost estimate。

## 13. 验收标准

- [ ] 用户只能选择真实支持格式。
- [ ] aspect ratio变化区分Crop与Adapt。
- [ ] Batch进度/失败清晰。
- [ ] 下载不会因签名过期重render。
- [ ] Exact Version/Manifest可追溯。

## 14. Definition of Done

```text
export UX E2E green
+ batch/retry/download scenarios green
```

完成 Phase 7，下一节点：NODE-61 Collaboration。
