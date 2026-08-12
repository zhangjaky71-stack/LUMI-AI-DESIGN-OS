# NODE-52 — Frontend App Shell

> Phase: 7 Frontend Product  
> Status: SPECIFIED / READY FOR IMPLEMENTATION  
> Priority: P0  
> Depends on: NODE-02, NODE-11, NODE-16  
> Produces: Next.js App Router 产品壳、Auth/导航/主题/错误边界/数据客户端/设计系统基础

---

## 1. 目标

建立整个 LUMI Web 产品的稳定壳层。此节点不实现复杂 Canvas/Agent 业务，但必须让后续页面共享统一的登录态、Organization/Workspace context、API Client、导航、错误/加载状态、快捷键和 UI tokens。

## 2. Route Map

```text
/
/login
/signup
/app
/app/projects
/app/projects/[projectId]
/app/brands
/app/assets
/app/team
/app/billing
/app/settings
/admin   # 权限后续
```

Project Workspace 子路由由 NODE-54/55 扩展。

## 3. App Router Boundary

- Server Components用于shell/初始数据、授权重定向等适合场景。
- Client Components仅用于真实交互、Canvas、stream、local state。
- 不把整个App标成 `use client`。
- API请求统一封装 generated client/query layer。

## 4. Layout

```text
RootLayout
├─ Auth/Session Provider bridge
├─ Org/Workspace Context
├─ Query Client
├─ Error/Toast layer
├─ Global shortcut manager
└─ AppLayout
   ├─ Sidebar
   ├─ Topbar
   └─ Main content
```

## 5. UI Tokens

定义产品UI design tokens：

```text
color
spacing
radius
shadow
typography
z-index
motion
```

这些是产品UI系统，不与用户品牌 Brand Tokens 混用。

## 6. API Client

使用 NODE-11 自动生成 TS client + thin query wrappers。禁止组件直接散落 `fetch('/api/...')`。

支持：

- request id；
- CSRF/session；
- typed errors；
- abort signal；
- retry只对安全读请求。

## 7. Query State

服务端数据使用 query cache；UI ephemeral state使用轻量client store。禁止把 Project业务真相只放 Zustand/localStorage。

## 8. Auth UX

- login/signup/logout；
- session expiry；
- invite accept入口；
- unauthorized organization切换；
- recent auth提示接口。

错误信息不泄露账户存在性。

## 9. Organization Switch

切换org：

```text
cancel old in-flight queries
clear scoped cache
reset project selection
navigate
```

cache key必须包含org id，防跨租户UI缓存泄漏。

## 10. Error Boundaries

至少：

```text
root error
route error
project workspace error
canvas crash boundary later
```

提供 request_id供支持排查，不向用户展示stack。

## 11. Loading / Empty

所有主页面定义 skeleton/empty/offline/retry，而不是无限spinner。

## 12. Accessibility

- keyboard focus ring；
- semantic navigation；
- aria labels；
- skip navigation；
- modal focus trap；
- reduced motion。

## 13. Telemetry

产品分析事件通过 adapter：

```text
page viewed
project opened
command initiated
```

不在前端analytics payload上传prompt/图片内容等敏感数据，除非明确数据政策允许。

## 14. Feature Flags

建立 typed client/server feature flag accessor；普通客户端不能修改server-enforced安全flag。

## 15. Tests

- auth redirect；
- org switch cache isolation；
- typed API error；
- error boundary；
- keyboard navigation；
- build SSR/client boundary；
- no secret in client bundle检查。

## 16. 验收标准

- [ ] 登录后进入稳定App Shell。
- [ ] Organization可切换且缓存隔离。
- [ ] generated API client投入使用。
- [ ] loading/error/empty规范。
- [ ] App不是全量Client Component。
- [ ] accessibility smoke通过。

## 17. Definition of Done

```text
app shell implemented
+ route/auth E2E green
+ client secret scan green
```

下一节点：NODE-53 Projects UI。
