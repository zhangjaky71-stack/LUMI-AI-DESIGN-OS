# NODE-66 — Security Hardening & Threat Model

> Phase: 9 Production Readiness  
> Status: **CORE IMPLEMENTED / VALIDATING / NOT COMPLETE**  
> Priority: P0 / RELEASE BLOCKER  
> Depends on: NODE-16, NODE-18, NODE-20, NODE-21, NODE-25, NODE-65  
> Current stacked base: `feat/node-65-audit-governance`  
> Current stacked head: `feat/node-66-security-hardening`  
> Produces: Threat Model、Security Test Corpus、HTTP/Browser Hardening、Trust Labels、Security Release Gate、SAST/SCA/Secret Scan integration 与 production security gap ledger

---

## 1. 目标

在 Staging/Production 前进行系统性安全加固。LUMI 是 Agent + 文件 + 浏览器 + Sandbox + 外部工具 + 多租户 + Billing + Platform Admin 系统，风险高于普通 CRUD SaaS，因此 Security 是 **Release Gate**，不是“以后优化”。

本节点只把**可以通过源码/测试证明的控制**记为已实现；任何依赖真实 ingress、云 Secret Manager、production Sandbox、真实 outbound transport、staging URL、第三方渗透或最新-head CI 的项目都保留为 P0，不能用接口/文档代替执行证据。

## 2. 冻结安全基线（2026-08-18）

当前节点以实施时官方 OWASP 发布为冻结输入：

```text
OWASP Top 10:2025
OWASP ASVS 5.0.0
OWASP API Security Top 10:2023
OWASP Top 10 for LLMs / GenAI Applications 2025
OWASP Top 10 for Agentic Applications (Dec 2025)
```

详细 trust boundary、威胁、control、test、owner、residual risk 见：

`docs/security/THREAT-MODEL.md`

版本必须显式冻结；后续更新通过新的 security-policy version review，不允许验收标准静默漂移。

## 3. Threat Model

STRIDE/attack-tree 覆盖：

```text
Internet → CDN/WAF/Ingress → Browser/Web → API
Browser → Upload → Object Storage → Worker
API → PostgreSQL/Redis/Broker
Agent Runtime → Model Gateway
Agent Runtime → Tool Gateway → Web/MCP/SaaS
Agent → Sandbox
Worker → untrusted media/files
Platform Admin → privileged operations → Governance Audit
Organization user/API token → tenant resources
```

当前 threat register 包含 TM-01 … TM-17，涵盖 BOLA、Session/CSRF、resource abuse、SSRF、Prompt Injection、Tool Misuse、Sandbox Escape、File Parser、Supply Chain、Secrets、Admin privilege、Audit、Billing bypass、MCP supply chain、Browser XSS/clickjacking、exception handling 和 false-green CI。

## 4. Access Control / BOLA

重点：

- cross-tenant Project/Task/Asset/Artifact/Run/Cost/Billing/Governance；
- nested resource tenant confusion；
- ID enumeration；
- role escalation；
- API token scope；
- Platform Admin 与 Organization OWNER 严格分离。

现有 per-node tenant tests 与 API contract tests 被纳入 NODE-66 corpus，但**完整自动维护的 two-tenant BOLA matrix 尚未对所有 route family 证明**，保持 `NODE66-GAP-102` P0。

## 5. Authentication / Session / HTTP Boundary

NODE-66 新增并真实挂载 FastAPI Security Middleware：

- 禁止 `access_token` / `refresh_token` / `api_key` / password / secret / card 等敏感 query 参数；
- 对可证明的 `Content-Length` JSON request 做 app-level size limit；
- API response 添加 CSP、nosniff、frame deny、no-referrer、Permissions-Policy、COOP/CORP；
- production mode 添加 HSTS。

边界：chunked/streamed body 的完整 byte limit 必须由 ingress/proxy 真实验证，仍是 P0。

## 6. Browser Security

`apps/web/next.config.ts` 已统一输出：

```text
Content-Security-Policy
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
Referrer-Policy: no-referrer
Permissions-Policy
Cross-Origin-Opener-Policy: same-origin
Strict-Transport-Security (production only)
```

NODE-66 static gate 会扫描 app source，禁止新增 `dangerouslySetInnerHTML` 和显式 credential query URL。

当前 CSP 为 Next compatibility 仍允许 inline script/style；nonce/hash CSP 属 residual hardening，不虚报关闭。

## 7. Prompt Injection / Agent Goal Hijack

新增 `ContextEnvelope` trust boundary：

```text
SYSTEM
USER
ADMIN_CONFIG
EXTERNAL_UNTRUSTED
TOOL_RESULT_UNTRUSTED
ASSET_EXTRACT_UNTRUSTED
```

规则：

- 外部网页、文档、Tool output、OCR/Asset extract 是数据，不是授权；
- untrusted context 不能 `authoritative=true`；
- untrusted context 不能 `can_authorize=true`；
- context 默认存 content SHA-256，不需要把恶意内容原文变成安全状态；
- 带 token/signature 的 source ref 拒绝进入 context。

恶意 fixture 已覆盖“忽略系统、提升权限、上传全部文件”的情况。

**生产 Agent context compiler/runtime 尚未端到端携带 trust label**，因此 Prompt Injection E2E 仍为 P0。

## 8. SSRF / Network

复用 NODE-25 已有 `SSRFPolicy` 和 regression：

```text
127.0.0.1
localhost
RFC1918
169.254.169.254 / metadata
IPv6 loopback/private
mixed public/private DNS answer
redirect public → metadata
pinned validated IP
no ambient Authorization/Cookie
restricted response MIME
response byte limit
```

MCP Registry 在**请求时**重新 DNS/IP validate，不信任注册时结果；MCP transport interface 明确要求连接 `target.pinned_ip`。

未关闭边界：所有 production Browser/Tool/MCP concrete HTTP transport 必须证明 pinned-IP connect、正确 Host/SNI 和 redirect revalidation；这是 `NODE66-GAP-104`。

## 9. File Upload / Untrusted Media

复用 Asset/Sandbox 已有测试：

- magic-byte MIME sniff；
- SVG script/event/external resource/XXE rejection；
- filename/path sanitize；
- signed URL checksum binding + TTL cap；
- archive path/link traversal rejection；
- artifact/output limits。

仍需生产证据：malware scan、decompression/zip bomb、EXIF/privacy policy、PDF/image/video parser isolation。

## 10. Sandbox

复用 NODE-21 local Docker backend：

```text
--network none
--read-only
--cap-drop ALL
no-new-privileges
UID/GID 65532
PID / CPU / memory / swap limits
nosuid,nodev tmpfs
readonly /workspace/input
no Docker socket
no host mounts
shell/curl/wget/docker/nsenter forbidden
provider/database/cloud secret env forbidden
bounded output + timeout
workspace/archive traversal validation
```

这代表**源码级 local backend 安全基线**，不代表 production runtime 已通过 escape test。Production seccomp/AppArmor/runtime/infra verification 保持 P0。

## 11. Secrets

已存在/新增：

- Gitleaks full-history Secret Scan；
- `.env.example` 明确 local-only；
- Sandbox long-lived secret env deny；
- NODE-65 Audit redaction；
- NODE-66 URL query credential deny；
- secret-bearing Context source ref deny。

Production Secret Manager/workload identity + rotation exercise仍是 P0。

## 12. Supply Chain

仓库已有：

```text
uv.lock / pnpm-lock.yaml
Dependency Review
CodeQL (Python + JavaScript/TypeScript, subject to repo policy)
Gitleaks
```

NODE-66 CI 增加 lock consistency 和跨模块 security corpus。

未关闭：container/IaC scan、SBOM、image digest/signature/provenance、生产 vulnerability exception evidence。

## 13. API Abuse / Denial of Wallet

已有：

- bounded JSON known-length request；
- API pagination caps；
- Tool/MCP catalog/response limits；
- Sandbox resource quotas；
- NODE-20 idempotency；
- NODE-63 billing/credit core。

仍需 production ingress rate limit、streamed body cap、generation concurrency/budget policy 和 credit runtime integration evidence。

## 14. Model / Tool Abuse

授权必须来自 server-side policy，而不是模型文本。

现有 NODE-25 Tool Gateway、NODE-62 Approval 设计与 NODE-66 trust labels 共同作为基础；所有 destructive/external-write production bindings 和 HITL inventory 尚需统一验收。

## 15. Admin Security

NODE-64 已实现独立 Platform Admin principal/RBAC、break-glass、安全 projection；Organization OWNER 不能自动获得平台后台权限。

仍需：

```text
global-admin auth/bootstrap
strong MFA / step-up
shorter privileged session
production dual-control rules
NODE-65 durable privileged Audit ingress
```

均保留 P0。

## 16. Security Release Gate

新增 `SecurityReleaseGate`：

```text
Critical: always blocks
High: blocks by default
High exception profile: explicit enable + owner + reason + short expiry
Medium OPEN: owner + due date required
Low: tracked
```

STOP SHIP：

```text
cross-tenant leak/write
sandbox/worker host escape
usable secret exposure
payment/credit bypass
repeated paid side effect
unaudited privileged mutation
production SSRF to internal/metadata
latest-head security CI not actually executing
```

## 17. Security Tooling / CI

NODE-66 release corpus 将执行：

- compile/static security acceptance；
- API HTTP/trust/release-gate tests；
- Tool Gateway SSRF tests；
- Sandbox security/archive/artifact tests；
- Asset security tests；
- Auth/API regressions；
- Web TypeScript/lint/build；
- lock consistency；
- CodeQL/Dependency Review/Gitleaks workflow presence；
- gap ledger fail-closed assertion。

Staging DAST、container/IaC/SBOM、独立 pentest 需要真实环境/工具执行，保持 open gate。

## 18. 验收状态

- [x] Threat model 覆盖主要 trust boundaries 并有 owner/control/test/residual risk。
- [ ] 完整 cross-tenant/BOLA corpus 全绿。
- [x] SSRF core fixtures 已存在并纳入 release corpus。
- [ ] Prompt Injection fixtures 通过 production Agent end-to-end。
- [x] Sandbox source-level isolation/escape-policy suite 已存在并纳入 corpus。
- [ ] Production-equivalent Sandbox escape suite 全绿。
- [x] CodeQL/Dependency Review/Gitleaks 已接仓库 CI。
- [ ] Container/IaC/SBOM/DAST production gates 执行。
- [x] API/Web security headers 与 query-secret gate 已实现。
- [ ] Secret Manager/workload identity/rotation 完成。
- [ ] Critical/High latest-head release gate满足并有 named Security sign-off。
- [ ] Independent penetration test完成。

## 19. Current P0 Source of Truth

`reports/nodes/NODE-66/gap-ledger.json`

当前状态必须保持：

`CORE_IMPLEMENTED_VALIDATING_NOT_COMPLETE`

直到所有 OPEN P0 以执行证据关闭。

## 20. Definition of Done

```text
threat model signed off
+ complete authorization / prompt / SSRF / sandbox security corpus green
+ SAST/SCA/secret/container/IaC/DAST evidence retained
+ production Secret/Admin/Audit controls verified
+ no release-blocking findings
+ independent penetration/red-team evidence
+ named Security approval
```

**NODE-66 当前尚未达到 Definition of Done。**

下一节点：NODE-67 Observability（只能在 NODE-66 release blocker 可追踪、不可被误判完成的前提下继续 stacked development）。
