# NODE-49 — Export Engine

> Phase: 6 Generation & Quality  
> Status: SPECIFIED / READY FOR IMPLEMENTATION  
> Priority: P0 / PRODUCT DELIVERY  
> Depends on: NODE-40, NODE-41, NODE-42, NODE-19  
> Produces: Raster/SVG/PDF/批量尺寸/项目包导出、Export Manifest、可靠下载

---

## 1. 目标

让设计成果真正可交付，而不是只存在Canvas预览。支持可复现的服务器/客户端导出、批量尺寸、多格式和provenance manifest。

## 2. Formats V1

```text
PNG
JPEG
WebP
SVG（仅结构支持的vector/text内容）
PDF
LUMI project package
ZIP batch package
```

视频格式由 NODE-48。

不承诺把任意单层AI raster自动变成真实可编辑PSD；只有源Design IR拥有分层结构时才可导出相应结构化格式/项目包。任何PSD支持需单独技术Node/ADR验证。

## 3. ExportSpec

```text
artifact/design version id
frame ids
format
target dimensions/scale
quality
background/alpha
color profile
bleed/crop marks optional
filename template
batch variants
include_manifest
```

## 4. Snapshot

Export永远针对 exact Artifact/DesignVersion，不针对浮动“最新”。Export开始后版本变化不影响此次结果。

## 5. Rendering

两条：

### Browser Preview Export
适合低延迟小图，但不是唯一production renderer。

### Server Render Worker
读取Design IR+资源+compiler version，在隔离media runtime渲染高分辨率/PDF/batch。

服务器必须加载许可字体并保持布局一致性。

## 6. Multi-size Adaptation

两种：

```text
SCALE/CROP export
DESIGN_ADAPTATION recipe
```

9:16→1:1若需要重新排版，先由 Agent/Layout创建独立DesignVersion，不在Export偷偷破坏版式。

## 7. Print

P1支持：

- mm/in unit conversion；
- DPI；
- bleed；
- crop marks；
- embedded fonts policy；
- CMYK/profile 需要实际 color management library/print tests后开启。

如果没有真实CMYK管理，不在UI声称“印刷级CMYK”。

## 8. SVG

只导出可安全表达的vector/text/image refs。用户字体可选择 convert-to-path（rights允许）或保留文本；sanitize外部 href。

## 9. PDF

页面=Frames；embedded/linked resources受控。PDF输出后用parser验证 page count、尺寸、可打开。

## 10. Export Job

```text
PENDING
RENDERING
PACKAGING
VALIDATING
READY
FAILED
EXPIRED
```

长导出走 queue/worker，Realtime展示进度。

## 11. Download

完成后ArtifactFile +短时 signed URL。ZIP/Export artifact有retention；重新下载可在retention内复用，不重复render。

## 12. Manifest

包含：

```text
project/artifact/version
export spec
files/checksums
source/provenance refs
brand rule version
rights summary
models used
created_at
```

不包含 provider secrets/full hidden prompts。

## 13. Filename

sanitize user/project names，防 path traversal；ZIP entries固定安全路径，防 zip-slip。

## 14. Tests

- exact version snapshot；
- PNG/JPEG/WebP dimensions；
- SVG sanitize；
- PDF open/page size；
- batch ZIP safe paths；
- Unicode filename；
- font fallback；
- signed URL auth；
- repeat export idempotent。

## 15. 验收标准

- [ ] 主流图片格式真实导出。
- [ ] PDF可验证打开。
- [ ] exact version保证。
- [ ] 批量导出/ZIP。
- [ ] manifest/checksum。
- [ ] 不虚假承诺PSD/CMYK能力。
- [ ] 下载经过授权/短时签名。

## 16. Definition of Done

```text
export worker/API implemented
+ format validation green
+ batch/package security green
```

下一节点：NODE-50 Visual Critic。
