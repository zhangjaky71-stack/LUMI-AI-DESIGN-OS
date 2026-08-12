# NODE-03 — Local Infrastructure

> Phase: -1 Engineering Foundation  
> Status: SPECIFIED / READY FOR IMPLEMENTATION  
> Priority: P0  
> Depends on: NODE-02  
> Produces: 一套无需云账号即可运行的本地生产近似基础设施

---

## 1. 目标

让开发者在 Windows 11 + WSL2 + Docker Desktop 或 Linux/macOS 环境中，通过一条命令启动 LUMI 所需基础依赖。所有后续 Node 必须首先能够在本地环境完成开发与自动测试，不能因为 AWS、支付、商业模型 Key 尚未开通而停工。

## 2. P0 本地服务

```text
PostgreSQL + pgvector
Redis
RabbitMQ
MinIO (S3-compatible)
Mailpit
```

可选 profile：

```text
Prometheus
Grafana
Jaeger/Tempo
```

Observability 完整栈到 NODE-67 再正式启用。

## 3. 为什么这样选

### PostgreSQL

业务唯一真相源，后续承载 User/Org/Project/Task/Artifact/Ledger/Audit/Outbox。P0 向量能力优先 pgvector，避免一开始引入独立 Vector DB。

### Redis

仅用于：

- cache；
- rate limit；
- ephemeral distributed lock；
- realtime coordination；
- short-lived state。

不得把 Redis 当业务真相源。

### RabbitMQ

媒体后台任务的 P0 broker。Celery 当前将 RabbitMQ/Redis 都列为稳定 broker；本架构选择 RabbitMQ 将消息职责和 Redis cache 职责分离。

### MinIO

模拟 S3 object storage。业务代码必须只依赖 S3-compatible adapter，开发环境 MinIO、生产环境 AWS S3/R2 等可以替换。

### Mailpit

邮件测试捕获器，用于注册/邀请/通知流程，不发送真实邮件。

## 4. Docker Compose 结构

```text
infra/compose/
├─ docker-compose.yml
├─ docker-compose.observability.yml
├─ env.local.example
└─ README.md
```

核心 service names 固定：

```text
postgres
redis
rabbitmq
minio
minio-init
mailpit
```

## 5. 默认端口

避免依赖默认端口在宿主机发生冲突，README 明确可覆盖：

```text
PostgreSQL   5432
Redis        6379
RabbitMQ     5672
RabbitMQ UI  15672
MinIO API    9000
MinIO UI     9001
Mailpit SMTP 1025
Mailpit UI   8025
```

生产不暴露管理端口到公网。

## 6. PostgreSQL 初始化

必须提供 init/migration 前置支持：

```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
```

数据库 schema 由 NODE-10 Alembic 管理；NODE-03 不提前创建业务表。

建立独立 DB user：

```text
lumi_app
lumi_migration
```

本地可简化密码，但不能复用到 staging/prod。

## 7. Object Storage 初始化

`minio-init` 自动创建：

```text
lumi-assets
lumi-exports
lumi-sandbox
```

建议 key 规则：

```text
org/{org_id}/project/{project_id}/...
```

浏览器上传未来通过 presigned URL，不将大文件转发经过 API 内存。

## 8. RabbitMQ 约定

P0 定义 logical queues：

```text
lumi.media.image
lumi.media.video
lumi.media.export
lumi.system.low
```

死信策略：

```text
<queue>.dlq
```

不在 NODE-03 实现真正 worker routing，但基础设施需支持后续 NODE-19。

## 9. Health Checks

Compose 每个 service 都必须 healthcheck；`depends_on` 使用 health condition，而不是固定 sleep。

统一脚本：

```bash
make infra-up
make infra-status
make infra-down
make infra-reset
```

`infra-reset` 是 destructive command，必须二次提示或显式 `CONFIRM=1`。

## 10. 应用连接检查

新增 `scripts/doctor`：

检查：

1. Docker daemon。
2. PostgreSQL TCP + SELECT 1。
3. vector extension。
4. Redis PING。
5. RabbitMQ connectivity。
6. MinIO bucket existence。
7. Mailpit endpoint。

输出人类可读结果和非零退出码。

## 11. 本地 Secret 策略

- Compose 默认凭证只用于 local。
- 所有密码由 `infra/compose/.env` 加载。
- `.env` gitignored。
- `.env.example` 包含明确 `LOCAL_ONLY` 标识。
- 不允许把任何云 Access Key 写入 compose 文件。

## 12. 数据持久化

Docker volumes：

```text
lumi_postgres_data
lumi_redis_data
lumi_rabbitmq_data
lumi_minio_data
```

测试环境可以使用 ephemeral volume；开发环境默认保留。

## 13. 测试

### Infrastructure smoke

- PostgreSQL `SELECT 1`。
- `CREATE EXTENSION vector` 已完成。
- Redis ping。
- RabbitMQ management health。
- MinIO PUT/GET round trip。
- Mailpit 接收一封测试邮件。

### Restart resilience

停止并重启 compose，PostgreSQL 和 MinIO 数据必须保留。

### Network boundary

应用容器使用内部 service DNS，不依赖 `localhost`。

## 14. 验收标准

- [ ] `make infra-up` 从空 Docker 环境启动所有服务。
- [ ] 所有 healthchecks 绿色。
- [ ] `make doctor` 返回 PASS。
- [ ] pgvector 可用。
- [ ] MinIO buckets 自动创建。
- [ ] RabbitMQ queues 后续可由 worker 声明。
- [ ] local environment 不需要 AWS/云账号。
- [ ] `make infra-down` 安全停止。
- [ ] 数据默认可跨 restart 保留。

## 15. 风险与控制

### Windows 文件系统性能

源码建议放 WSL2 Linux filesystem，不建议放 `/mnt/c` 进行高频 node_modules/venv I/O。

### Docker 资源

媒体任务后期资源高；P0 local worker 默认 concurrency=1，并提供 profile 控制。

### Redis 误用

代码评审禁止把只有 Redis 的状态作为余额、Artifact 或 Project 的唯一来源。

## 16. Definition of Done

```text
compose infrastructure committed
+ doctor passes
+ persistence verified
+ MinIO round-trip test passes
+ README local runbook complete
```

下一节点：NODE-04 CI Foundation。
