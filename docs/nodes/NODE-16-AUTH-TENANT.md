# NODE-16 — Authentication & Tenant Isolation

> Phase: 2 Runtime Foundation  
> Status: SPECIFIED / READY FOR IMPLEMENTATION  
> Priority: P0 / SECURITY  
> Depends on: NODE-10, NODE-11  
> Produces: 登录、Session、Organization/Workspace membership、RBAC、Tenant guard

---

## 1. 目标

建立无需第三方 Auth SaaS 也能开发/运行的 P0 身份系统，同时保留 OIDC/SAML 扩展边界。任何 Project、Asset、Artifact、AgentRun、Cost 数据都必须经过 tenant authorization。

## 2. P0 身份模式

支持：

- email + password；
- email verification adapter；
- secure browser session；
- organization membership；
- invitation；
- external API token/service token 基础结构。

P1：Google/Microsoft OIDC、MFA；Enterprise：SAML/SCIM。

## 3. Password

- Argon2id hash。
- 每用户随机 salt（由库管理）。
- 不自行实现密码学。
- password reset token 只存 hash，短时过期，单次使用。
- 登录错误不得暴露“邮箱是否存在”。

## 4. Browser Session

首选 opaque session id + server-side session record，而不是把大量权限状态塞进长寿命 JWT。

Cookie：

```text
HttpOnly
Secure (非 local)
SameSite=Lax/Strict according to flow
Path=/
```

Session：

```text
id
user_id
created_at
expires_at
last_seen_at
revoked_at
user_agent_hash?
ip_risk_metadata?
```

敏感操作可要求 recent authentication。

## 5. CSRF

Cookie-authenticated mutating request 必须有 CSRF protection：SameSite + origin check + CSRF token/double-submit 或框架成熟机制。不得认为 CORS 等于 CSRF 防护。

## 6. Organization / Workspace

```text
User
  ↓ membership
Organization
  ↓
Workspace
  ↓
Project
```

P0 role：

```text
OWNER
ADMIN
EDITOR
VIEWER
BILLING
```

组织 owner 至少保留一人，不能把最后一个 owner 降级/删除。

## 7. Permissions

不要在 handler 中散落 `role == admin`。

统一：

```text
project.read
project.write
asset.upload
artifact.approve
brand.manage
member.invite
billing.read
billing.manage
admin.audit.read
```

AccessPolicyService 输入 actor + resource + action，返回 allow/deny/reason code。

## 8. Tenant Guard

Repository 接口必须传 `organization_id`。禁止：

```python
repo.get(project_id)
```

要求：

```python
repo.get(organization_id, project_id)
```

cross-tenant ID 应返回一致的 not-found/forbidden policy，避免枚举资源。

## 9. Request Context

每请求构建：

```text
request_id
actor_id
organization_id
workspace_id?
roles
permissions
trace_id
```

日志和 audit 自动带 tenant，不靠业务手填。

## 10. Invite Flow

```text
Admin creates invite
→ random high-entropy token
→ store token hash + email + role + expiry
→ Mail adapter
→ accept
→ create/attach user
→ membership transaction
→ invite consumed
```

本地 Mailpit；生产邮件 provider 后接。

## 11. API Tokens

P0 schema 预留：

```text
api_token_id
organization_id
name
prefix
secret_hash
scopes
expires_at
last_used_at
revoked_at
```

明文 token 只显示创建一次。

## 12. Rate Limit

登录、reset、invite accept 独立 rate limit。Redis 只是计数协调；封禁/安全审计需 DB event。

## 13. Audit

必须记录：

```text
login success/failure category
logout
password changed/reset
session revoked
invite created/accepted/revoked
membership role changed
API token created/revoked
```

不记录密码/token 明文。

## 14. Tests

- password hash verify；
- session expiry/revoke；
- CSRF negative；
- role matrix；
- cross-tenant read/write；
- last-owner invariant；
- invite replay；
- reset token replay；
- API token scope。

## 15. 验收标准

- [ ] 本地可注册/登录/登出。
- [ ] Session secure contract 完成。
- [ ] Org/Workspace membership 可用。
- [ ] RBAC permission matrix 有测试。
- [ ] cross-tenant integration suite 通过。
- [ ] password/reset/invite token 不存明文。
- [ ] Auth events 进入 Audit。

## 16. Definition of Done

```text
auth flows implemented
+ RBAC tests green
+ tenant leak tests green
+ session security reviewed
```

下一节点：NODE-17 Project Core。
