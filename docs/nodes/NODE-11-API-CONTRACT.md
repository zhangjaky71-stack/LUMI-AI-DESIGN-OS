# NODE-11 — API Contract

> Phase: 1 Domain / Contract  
> Status: SPECIFIED / READY FOR IMPLEMENTATION  
> Priority: P0  
> Depends on: NODE-09, NODE-10  
> Produces: `/v1` REST API、OpenAPI、错误模型、分页/幂等/上传合同、Generated TS Client

---

## 1. 目标

先冻结外部 API 语义，再实现业务 handler。Web 前端、Admin、未来 SDK 都只依赖公开 contract，不 import 后端内部 Python 对象。

## 2. API Style

P0：REST/JSON + SSE。

```text
HTTPS REST: commands/query
SSE: agent/task streaming
WebSocket: 后续实时协作专用
```

不在 P0 引入 GraphQL。

## 3. Base

```text
/api/v1
```

路径使用复数资源、lowercase kebab/简单 nouns。

## 4. Authentication

HTTP：

```http
Authorization: Bearer <token>
```

浏览器产品可用 secure httpOnly session cookie，由 BFF/session layer 换取/验证身份；外部 API 使用 bearer/service token。

所有响应都不返回 Secret。

## 5. Error Contract

采用 RFC 7807 风格 Problem Details：

```json
{
  "type": "https://errors.lumi.dev/project/not-found",
  "title": "Project not found",
  "status": 404,
  "code": "PROJECT_NOT_FOUND",
  "detail": "...",
  "request_id": "...",
  "fields": {}
}
```

前端逻辑依赖稳定 `code`，不解析英文 message。

## 6. Pagination

列表使用 cursor pagination：

```http
GET /projects?limit=50&cursor=...
```

响应：

```json
{
  "items": [],
  "next_cursor": null,
  "has_more": false
}
```

禁止大表默认 offset pagination。

## 7. Concurrency

可编辑资源返回：

```text
version
```

update 请求携带：

```http
If-Match: "<version-or-etag>"
```

冲突返回 `409 VERSION_CONFLICT`，前端提示刷新/合并。

## 8. Idempotency

所有可能产生付费/外部副作用的 POST：

```http
Idempotency-Key: <uuid>
```

服务端通过 NODE-20 处理。缺失时对公开客户端可拒绝或生成仅限非关键 command 的 request key。

## 9. Upload

大文件直接 S3：

```text
POST /assets/uploads
→ presigned upload contract
→ browser PUT multipart/direct
→ POST /assets/uploads/{id}/complete
```

API 不代理数百 MB 视频 body。

## 10. P0 Endpoint Groups

### Identity / Organization

```text
GET    /me
GET    /organizations
GET    /organizations/{id}
GET    /organizations/{id}/members
POST   /organizations/{id}/invites
```

### Projects

```text
GET    /projects
POST   /projects
GET    /projects/{id}
PATCH  /projects/{id}
DELETE /projects/{id}
POST   /projects/{id}/archive
```

### Assets

```text
POST /assets/uploads
POST /assets/uploads/{upload_id}/complete
GET  /assets
GET  /assets/{id}
DELETE /assets/{id}
```

### Brands

```text
GET/POST /brands
GET/PATCH /brands/{id}
GET/POST /brands/{id}/rules
```

### Agent Runs

```text
POST /projects/{id}/agent-runs
GET  /agent-runs/{id}
POST /agent-runs/{id}/cancel
POST /agent-runs/{id}/resume
GET  /agent-runs/{id}/stream
```

### Tasks

```text
GET /projects/{id}/tasks
GET /tasks/{id}
```

### Artifacts

```text
GET  /projects/{id}/artifacts
GET  /artifacts/{id}
GET  /artifacts/{id}/versions
POST /artifact-versions/{id}/approve
POST /artifact-versions/{id}/restore
```

### Design

```text
GET  /design-documents/{id}
POST /design-documents/{id}/operations
```

### Billing/Usage

```text
GET /usage
GET /costs/summary
```

## 11. Command Endpoint Response

长任务不阻塞 HTTP 到模型结束：

```http
POST /projects/{id}/agent-runs
202 Accepted
```

返回：

```json
{
  "run_id": "...",
  "status": "PENDING",
  "stream_url": "/api/v1/agent-runs/.../stream"
}
```

## 12. SSE Contract

```text
event: agent.status
data: {...}

id: <event-sequence>
```

支持 reconnect，客户端发送 `Last-Event-ID`；服务端只保证文档定义的 retention window。

## 13. Schema Generation

Pydantic → OpenAPI 是 canonical HTTP schema 来源。

CI：

```text
generate openapi.json
→ generate TypeScript client
→ git diff --exit-code
```

防止前后端 contract drift。

## 14. API Versioning

- Breaking contract → `/v2` 或版本化 media type/明确 migration；P0 以 `/v1` 为主。
- 新 optional field 不算 breaking。
- 删除/改语义必须 deprecation window。

## 15. Security

- Object authorization 每个 endpoint 检查 tenant。
- user-supplied URL 禁止任意 server fetch（SSRF）。
- file content type 不信任客户端声明。
- pagination/filter 输入有上限。
- request body size limit。
- API error 不泄露 stack/SQL/provider secret。

## 16. Contract Tests

- OpenAPI valid。
- generated client builds。
- error format consistent。
- cursor stable。
- If-Match conflict。
- idempotency header contract。
- unauthorized/cross-tenant 404/403 policy consistent。
- SSE reconnect。

## 17. 验收标准

- [ ] `/api/v1` OpenAPI 生成。
- [ ] TS client 自动生成并编译。
- [ ] 所有 P0 resource 有 endpoint contract。
- [ ] Problem Details 统一。
- [ ] cursor/idempotency/concurrency 规范冻结。
- [ ] 大文件上传走 presigned flow。
- [ ] 长任务使用 202 + stream，不长连接等结果。

## 18. Definition of Done

```text
OpenAPI contract committed
+ generated TS client green
+ contract tests green
+ API style guide frozen
```

下一节点：NODE-12 Event Protocol。
