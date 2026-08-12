# NODE-04 — CI Foundation

> Phase: -1 Engineering Foundation  
> Status: SPECIFIED / READY FOR IMPLEMENTATION  
> Priority: P0  
> Depends on: NODE-02, NODE-03  
> Produces: GitHub Actions 质量门禁、依赖缓存、基础安全扫描和可复现 CI

---

## 1. 目标

任何后续代码在进入主分支前，都必须自动证明“能安装、能编译、类型正确、单元测试通过、没有明显 secret 泄漏”。CI 从项目第一天开始，而不是上线前补。

## 2. Workflow 划分

```text
.github/workflows/
├─ ci.yml
├─ dependency-review.yml
├─ secret-scan.yml
└─ codeql.yml          # 可在仓库权限支持时启用
```

P0 主流程 `ci.yml` 不依赖商业 API Key。

## 3. CI Jobs

### job: changes

识别 TS/Python/docs/infra 变更，允许后续做 path-aware optimization，但不得因为优化而漏测核心 contract。

### job: frontend

执行：

```bash
pnpm install --frozen-lockfile
pnpm lint
pnpm typecheck
pnpm test
pnpm build
```

### job: python

执行：

```bash
uv sync --frozen
uv run ruff format --check .
uv run ruff check .
uv run pyright
uv run pytest
```

### job: contracts

从 P0 起预留：

```text
JSON Schema validation
OpenAPI validation
Event schema validation
Design IR fixtures
```

NODE-11～15 后逐步启用。

### job: integration

使用 GitHub Actions service containers 或 Docker Compose 启动：

```text
PostgreSQL
Redis
RabbitMQ
MinIO
```

运行最小 infrastructure integration tests。

## 4. CI 运行矩阵

首版不要做庞大 matrix：

- Node: 24 LTS only。
- Python: 3.12 only。
- Ubuntu runner。

跨版本兼容测试放定期 workflow，而非所有 PR。

## 5. Cache

缓存：

- pnpm store；
- Turborepo cache（先 GitHub cache，后续可 remote cache）；
- uv cache；
- Playwright browsers 只在 E2E workflow 安装。

缓存 key 必须包含 lockfile hash。

## 6. Branch Gate

`main` 目标 required checks：

```text
frontend
python
contracts
integration
secret-scan
```

如果 GitHub 仓库策略当前无法自动由 connector 配置，文档记录为 repository setting action，在实施时通过 API/人工一次性设置。

## 7. Secret Safety

CI 禁止输出：

```text
.env
Authorization headers
Provider API Keys
database password
presigned URL query strings
```

启用：

- GitHub secret scanning（仓库能力允许时）。
- gitleaks 或等价 OSS scanner 作为 repo-level fallback。
- `.env.example` allowlist。

## 8. Dependency Security

P0：

- `pnpm audit` 不作为唯一安全门，因为 registry audit 噪声可能高；使用 dependency review + periodic audit。
- `uv audit` 或 pip ecosystem audit 运行在定时 job。
- lockfile 必须提交。

P1：生成 SBOM（CycloneDX/SPDX）。

## 9. Test Artifacts

失败时上传：

```text
pytest junit
vitest junit
Playwright report
coverage report
contract diff
```

禁止上传包含 user content 或 secrets 的实际生产数据。

## 10. Coverage 策略

初期不追求虚假的 100%。门槛按域逐步提高：

```text
Domain/contract packages     >= 90%
Gateway routing logic        >= 85%
Security/billing/idempotency >= 90%
UI components                >= 70%
```

NODE-04 先建立 report，不因为空 scaffold 强设门槛；从相关 Node 实施后开启。

## 11. Commit / PR 规则

建议 conventional-ish commit：

```text
feat:
fix:
docs:
test:
refactor:
infra:
```

Node 实施提交必须在 message/body 中包含 `NODE-XX`。

示例：

```text
feat(api): bootstrap project core (NODE-17)
```

## 12. Generated Files

API client、schema snapshot 等 generated artifact 必须有明确策略：

- 如果前端构建依赖且生成稳定，则提交 snapshot。
- CI 重新生成并检查 `git diff --exit-code`，防止 stale generated files。

## 13. CI 时间目标

P0 PR 快速门：

```text
P50 < 6 min
P95 < 12 min
```

耗时 AI benchmark、真实 provider integration、长视频渲染不得放普通 PR blocking path；进入 nightly/release gate。

## 14. 测试本身的测试

建立故障注入 sanity：

1. 临时 lint error 应让 frontend job fail。
2. 临时 Python failing test 应 fail。
3. 修改 lockfile 不一致应 fail frozen install。
4. 合入前恢复。

这是验证 CI 真的阻止坏代码，而不是“总是绿色”。

## 15. 验收标准

- [ ] Push/PR 会自动运行 CI。
- [ ] TS lint/typecheck/test/build 通过。
- [ ] Python lint/typecheck/test 通过。
- [ ] integration services 可启动并测试。
- [ ] frozen lockfile install。
- [ ] secret scanner 生效。
- [ ] CI 不依赖任何付费模型 key。
- [ ] 失败测试能阻断 workflow。
- [ ] artifacts 可用于定位失败。

## 16. 回滚

如果某新检查误报严重，可以临时变为 non-blocking，但必须：

1. 创建 issue/ADR；
2. 记录恢复 blocking 的条件；
3. 不能删除检查伪装成通过。

## 17. Definition of Done

```text
CI workflows committed
+ clean PR simulation green
+ deliberate failure simulation red
+ lockfile reproducibility proven
+ secrets not exposed
```

完成后 Engineering Foundation 结束，进入 Phase 0：NODE-05 Benchmark Harness。
