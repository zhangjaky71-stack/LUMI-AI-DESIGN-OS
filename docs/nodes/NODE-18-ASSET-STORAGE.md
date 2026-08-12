# NODE-18 — Asset Storage

> Phase: 2 Runtime Foundation  
> Status: SPECIFIED / READY FOR IMPLEMENTATION  
> Priority: P0  
> Depends on: NODE-17, NODE-03, NODE-15  
> Produces: S3-compatible 上传/下载、资产验证、metadata、preview pipeline、安全 storage adapter

---

## 1. 目标

安全管理用户图片、视频、Logo、字体、参考文件和生成物的 binary storage。大文件不穿过 API 内存，浏览器通过短时 presigned URL 直传 Object Storage。

## 2. Storage Adapter

```text
ObjectStore
├─ create_upload
├─ complete_upload
├─ head
├─ get_signed_download
├─ copy
├─ delete_candidate
└─ multipart operations
```

Dev: MinIO。Prod: S3-compatible provider。

## 3. Key Strategy

不要用用户原文件名直接作为 key：

```text
org/{org_id}/project/{project_id}/asset/{asset_id}/original/{file_id}
```

文件名作为 metadata，经 sanitize 后仅用于 download disposition。

## 4. Upload Lifecycle

```text
POST create-upload
→ DB UploadSession PENDING
→ presigned PUT/multipart
→ client upload
→ complete-upload
→ HEAD/checksum verify
→ Asset SCANNING
→ validation worker
→ READY | REJECTED
```

没有 complete/verify 的孤立 upload 由 TTL cleanup。

## 5. Integrity

要求：

- size limit；
- checksum；
- object existence；
- content length；
- MIME sniffing。

不信任 `Content-Type` 和扩展名。

## 6. Supported P0

图片：

```text
PNG JPEG WebP
```

设计/向量：

```text
SVG（严格 sanitize）
PDF（作为 asset，不执行脚本）
```

视频：

```text
MP4/MOV/WebM 根据 ffprobe 可解析
```

字体：TTF/OTF/WOFF2，上传前/后需要授权声明与字体解析验证。

## 7. SVG Security

SVG 是主动内容风险。上传后 sanitizer 必须移除/拒绝：

```text
<script>
foreign external URL
javascript: URL
事件 handler
危险 external entity/resource
```

生产渲染时不要直接 unsanitized innerHTML。

## 8. Malware Scan

P0 接口：`FileScanner`。

Local 可 ClamAV container/可配置 scanner；没有 scanner 时生产 readiness 不允许默认为“安全”，必须标 `SCAN_UNAVAILABLE` 并按环境 policy 阻止高风险文件。

## 9. Metadata Extraction

图片：width/height/color profile/alpha/exif safe subset。

视频：duration/resolution/fps/codec via ffprobe。

字体：family/style/license metadata if available。

默认剥离或不公开敏感 EXIF（GPS）。

## 10. Preview Pipeline

生成：

```text
thumbnail
medium preview
poster frame (video)
```

原文件 immutable；preview 是 derived AssetFile。

## 11. Downloads

API authorization 后返回短时 signed URL。URL：

- TTL 短；
- 不写日志完整 query；
- 对敏感文件 Content-Disposition attachment；
- public project/CDN 以后单独设计。

## 12. Quota

上传前检查：

```text
plan file size limit
org storage quota
project policy
media type
```

最终计费以 verified object size 为准，而不是客户端声明。

## 13. Rights Metadata

用户上传必须记录来源/rights assertion：

```text
USER_OWNED
LICENSED
UNKNOWN
```

不因为“上传成功”自动变 `commercial_use=true`。

## 14. Events

```text
asset.upload.created
asset.upload.completed
asset.scan.failed
asset.ready
asset.rejected
asset.preview.created
```

## 15. Tests

- presigned create/complete；
- wrong checksum；
- oversized；
- fake extension MIME；
- malicious SVG fixtures；
- cross-tenant download；
- expired signed URL contract；
- orphan cleanup；
- preview generation。

## 16. 验收标准

- [ ] Browser 可直传 MinIO/S3 adapter。
- [ ] API 不代理大文件。
- [ ] complete 后验证 checksum/size/type。
- [ ] SVG 有 sanitizer。
- [ ] preview pipeline 工作。
- [ ] signed download 必须先 authorization。
- [ ] Asset 有 rights/source metadata。

## 17. Definition of Done

```text
upload/download round trip green
+ security fixtures green
+ preview pipeline green
+ storage adapter swappable
```

下一节点：NODE-19 Queue / Event Runtime。
