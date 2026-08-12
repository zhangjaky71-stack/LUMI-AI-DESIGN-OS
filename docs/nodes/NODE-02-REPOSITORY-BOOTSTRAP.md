# NODE-02 — Repository Bootstrap

> Phase: -1 Engineering Foundation  
> Status: **COMPLETE**  
> Implementation Status: **COMPLETE**  
> Priority: P0  
> Depends on: NODE-00, NODE-01  
> Produces: 可编译、可测试、可扩展的 LUMI monorepo 工程骨架  
> Implemented Commit: `cb78eedbafcbdc0952254a1db13a70c8052c1d44`  
> Acceptance Report: `reports/nodes/NODE-02/acceptance.md`  
> Validated Workflow: `NODE-02 Bootstrap` / Run `31584394850`  
> Implemented At: `2026-08-12`

---

## Implementation Result

NODE-02 已按本规格完成真实工程实现。最终 CI 直接执行 `make check`，随后执行 Web/Admin production build 与 Chromium Playwright `/health` smoke，全部通过。两份 lockfile 已提交并在最终验证中保持一致；不需要任何商业模型 API Key 即可完成本节点验收。

---

## 1. 目标

建立 LUMI AI Design OS 的真实工程仓库结构，使后续所有 Node 都在同一个可复现、可锁版本、可测试的基础上实现。此节点不实现业务功能，但必须让 Web、API、Agent Runtime、Media Worker 和共享 Package 能够独立启动并通过 smoke test。

成功标准不是“建几个空目录”，而是：

```text
clone repo
   ↓
安装 Node/Python 工具链
   ↓
安装锁定依赖
   ↓
执行统一 bootstrap
   ↓
Web/API/Agent/Worker 均可启动
   ↓
lint/typecheck/test 全绿
```

## 2. 技术基线

### 2.1 TypeScript / Web

- Node.js 24 LTS。
- pnpm workspace，根目录只保留一个 `pnpm-lock.yaml`。
- Turborepo 负责任务编排与缓存；如果后续证明不需要，可通过 ADR 移除，但 P0 使用。
- React 19.2 stable。
- Next.js App Router，TypeScript strict。
- Tailwind CSS 只承担应用 UI，不作为 Canvas scene 数据模型。
- ESLint + TypeScript compiler。
- Vitest：TS 单元/组件级逻辑测试。
- Playwright：浏览器 E2E。

### 2.2 Python

- Python 3.12 作为 P0 固定运行时；不要在首版使用 3.14 作为强制基线。
- uv 管理 Python、workspace、虚拟环境和 `uv.lock`。
- FastAPI 作为业务 API。
- Pydantic v2 contract。
- pytest。
- Ruff format/lint。
- Pyright strict-ish type checking；逐步收紧，不允许 `Any` 扩散到 Domain Contract。

### 2.3 Repo 版本锁定

必须提交：

```text
.node-version
.python-version
pnpm-lock.yaml
uv.lock
```

禁止生产构建依赖 `latest` 浮动解析。

## 3. 目标目录

```text
LUMI-AI-DESIGN-OS/
├─ apps/
│  ├─ web/                  # Next.js 产品前端
│  ├─ api/                  # FastAPI 业务 API
│  ├─ agent-runtime/        # LangGraph + Deep Agents
│  ├─ worker-media/         # Celery/media worker
│  └─ admin/                # 后期 Admin，可先 scaffold
│
├─ packages/
│  ├─ design-ir/            # Design IR schema/runtime TS
│  ├─ design-constraints/   # constraint contract/runtime
│  ├─ event-schema/         # versioned domain events
│  ├─ api-client/           # generated TS client
│  ├─ canvas-sdk/           # Canvas public contract
│  ├─ artifact-sdk/         # Artifact contract
│  └─ ui/                   # shared application components
│
├─ services/
│  ├─ model-gateway/
│  ├─ tool-gateway/
│  ├─ sandbox-runtime/
│  ├─ memory/
│  ├─ knowledge/
│  ├─ visual-critic/
│  └─ asset-intelligence/
│
├─ agents/
├─ skills/
├─ recipes/
├─ evals/
├─ db/
│  ├─ migrations/
│  └─ seeds/
├─ infra/
│  ├─ compose/
│  ├─ docker/
│  └─ terraform/
├─ scripts/
├─ docs/
│  ├─ nodes/
│  ├─ adr/
│  └─ runbooks/
├─ .github/workflows/
├─ package.json
├─ pnpm-workspace.yaml
├─ turbo.json
├─ pyproject.toml
├─ uv.lock
├─ Makefile
├─ .env.example
└─ README.md
```

## 4. Workspace 规则

### 4.1 TypeScript

`pnpm-workspace.yaml` 至少包含：

```yaml
packages:
  - apps/web
  - apps/admin
  - packages/*
```

Python 服务不要伪装成 npm package。

### 4.2 Python uv workspace

根 `pyproject.toml` 统一声明 Python workspace members：

```text
apps/api
apps/agent-runtime
apps/worker-media
services/model-gateway
services/tool-gateway
services/sandbox-runtime
services/memory
services/knowledge
services/visual-critic
services/asset-intelligence
```

共享 Python 包放 `packages-py/`（若实现阶段确有需要），而不是跨目录 `sys.path` hack。

## 5. 应用最小契约

NODE-02 必须创建可运行的最小入口。

### Web

- `/`：显示 LUMI bootstrap page。
- `/health`：构建时可访问的简单页面。

### API

```http
GET /health/live
GET /health/ready
GET /version
```

返回至少：

```json
{
  "service": "api",
  "status": "ok",
  "version": "0.0.0-dev"
}
```

### Agent Runtime

- 可以 import LangGraph、LangChain、Deep Agents 包。
- 提供 CLI smoke command，不在本节点调用付费模型。

### Media Worker

- Celery app 可以 import。
- 提供 `health.ping` task，但 NODE-03 才连接 broker。

## 6. 配置策略

建立统一配置命名：

```text
LUMI_ENV
LUMI_LOG_LEVEL
DATABASE_URL
REDIS_URL
RABBITMQ_URL
S3_ENDPOINT_URL
S3_BUCKET
LANGSMITH_API_KEY
```

规则：

1. `.env.example` 只含假值和说明。
2. `.env` 必须在 `.gitignore`。
3. Python 使用 typed Settings class。
4. TS 对公开变量与服务器变量分离，禁止把 server secrets 暴露为 `NEXT_PUBLIC_*`。
5. 应用启动时对必需变量 fail-fast。

## 7. 根命令

提供统一入口，避免小白必须记几十条命令：

```bash
make bootstrap
make dev
make lint
make typecheck
make test
make check
```

`make check` 必须依次完成 format-check、lint、typecheck、unit tests。

## 8. README 必须包含

- 项目是什么。
- Windows 11 推荐使用 WSL2 + Docker Desktop。
- 安装 Node 24 LTS、pnpm、uv、Docker。
- 一条命令 bootstrap。
- 一条命令启动本地依赖。
- 一条命令启动应用。
- 常见端口表。
- Secret 安全说明。
- 指向 `docs/NODE-INDEX.md`。

## 9. 测试计划

### Static

- TypeScript strict 编译成功。
- Python import graph 成功。
- Ruff/ESLint 通过。
- 未提交 secret。

### Smoke

- Web build 成功。
- API TestClient `/health/live` = 200。
- Agent Runtime import smoke 成功。
- Worker app import smoke 成功。

### Reproducibility

在全新环境：

```text
pnpm install --frozen-lockfile
uv sync --frozen
```

必须成功。

## 10. 验收标准

- [x] 目录结构符合 Architecture V2。
- [x] Node 24 LTS 与 Python 3.12 被固定。
- [x] `pnpm-lock.yaml`、`uv.lock` 均存在。
- [x] Web/API/Agent/Worker 均有真实入口。
- [x] `make check` 一次通过。
- [x] 不需要任何真实商业 API Key 即可验收。
- [x] `.env.example` 完整且无 Secret。
- [x] README 可让全新开发机完成 bootstrap。

## 11. 禁止项

- 不实现具体 Agent 业务逻辑。
- 不直接调用 OpenAI/Google/图像模型。
- 不先做 Kubernetes。
- 不在 Web 中硬编码 API host。
- 不把 Python 与 TS 依赖混入同一包管理器。

## 12. 回滚

该节点为 scaffold，无数据库变更。若依赖选择失败，通过同节点 ADR 调整并重新生成 lockfile；禁止通过删除 Architecture V2 边界来“解决”构建问题。

## 13. Definition of Done

以下全部已完成：

```text
repository scaffold committed
+ lockfiles committed
+ all health/smoke tests pass
+ README onboarding verified
+ no secret in git
+ make check pass
+ production build pass
+ browser smoke pass
```

**NODE-02 = COMPLETE**

下一节点：NODE-03 Local Infrastructure。
