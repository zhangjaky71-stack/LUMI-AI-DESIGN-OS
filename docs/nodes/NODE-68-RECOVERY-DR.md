# NODE-68 — Backup, Recovery & Disaster Readiness

> Phase: 9 Production Readiness  
> Status: SOURCE IMPLEMENTED / RELEASE BLOCKED  
> Priority: P0 / RELEASE BLOCKER  
> Depends on: NODE-19, NODE-20, NODE-28, NODE-42, NODE-67  
> Produces: Backup/PITR、Object恢复、Run/Queue恢复、DR Runbooks、RPO/RTO与演练报告

---

## 0. Implementation Status — 2026-08-15

Source baseline 已实现：

- fail-closed recovery planner：safe requeue / external reconcile / checkpoint resume / preserve wait / manual review；
- `ambiguous`、已有 `provider_request_id`、外部状态不确定时禁止 blind retry；
- PostgreSQL WAL archive + verified base backup + isolated named restore-point PITR harness；
- MinIO versioning + delete/rewind/recover drill；
- restored DB read-only invariants 与 recovery workload inventory；
- DB/Object/Queue/AgentRun/Bad Deploy/Provider Outage/Security Incident 七份 runbook；
- `Recovery Contract` PR source gate + manual destructive drill；
- Makefile recovery 一键入口。

**尚未完成 Release 验收**：当前环境没有成功执行真实 runner drill，也没有 production-like restore、真实生产备份安全控制与 RPO/RTO 测量。因此本 NODE 仍是 RELEASE BLOCKED，下面第 16 节验收项保持未勾选。

Release Evidence：`docs/release-evidence/NODE-68-RECOVERY-DR-RELEASE-EVIDENCE.md`。

## 1. 目标

证明系统在数据库故障、部署错误、worker崩溃、provider结果不确定、误删和区域故障场景下可以恢复。只有“配置了backup”不算完成，必须真实restore演练。

## 2. Data Classification

```text
PostgreSQL: critical source of truth
Object Storage: critical user/artifact binary
LangGraph checkpoints: critical for resumable runs
Redis: rebuildable ephemeral
RabbitMQ: durable in-flight but not sole truth
LangSmith telemetry: operational, not business source
```

## 3. RPO/RTO Initial Targets

上线初期目标：

```text
PostgreSQL RPO <= 5 min target, RTO <= 60 min target
Object Storage RPO near-zero/versioned replication policy where supported
Redis RPO = acceptable rebuild for cache/presence
Agent in-flight: resume/reconcile, no duplicate paid effect
```

企业/SLA阶段再收紧。实际云能力与成本在NODE-72冻结。

## 4. PostgreSQL

Production要求：

- automated backup；
- point-in-time recovery；
- encrypted snapshot；
- separate backup retention；
- restore到isolated environment test；
- migration metadata一致。

## 5. Object Storage

- versioning；
- lifecycle；
- encryption；
- checksum；
- accidental delete protection；
- optional cross-region replication P1/enterprise。

DB restore后运行reconciliation识别missing/orphan objects。

## 6. Redis

Cache/presence可丢；系统必须能从DB恢复。Rate-limit reset不能造成安全失控，恢复后采取保守defaults。

## 7. RabbitMQ / Jobs

关键job状态在DB。Broker丢失后：

```text
scan DB jobs PENDING/RUNNING uncertain
→ reconcile operation/provider
→ requeue safe work
```

不从队列内容猜业务真相。

## 8. LangGraph Runs

场景：Agent Runtime重启。

要求：

- durable checkpoint；
- run状态映射；
- WAITING_USER可继续；
- WAIT_EXTERNAL查询job/provider；
- stale graph version按migration/old runtime策略；
- side effect幂等。

## 9. Provider Uncertain State

Runbook：

```text
provider request sent
local process died
→ use provider_request_id reconcile
→ if success collect result
→ if pending continue wait
→ if unknown flag ambiguous/manual policy
```

绝不盲目再次付费。

## 10. Deployment Rollback

App image immutable tag/digest；DB migration遵循expand/contract。Code rollback前检查schema兼容，不能简单回滚binary却数据库已breaking。

## 11. Disaster Scenarios

必须演练：

1. API/agent container全部重启；
2. media worker crash；
3. Redis flush；
4. RabbitMQ重建；
5. DB restore到新实例；
6. Object误删/恢复；
7. bad deploy rollback；
8. provider outage；
9. region级恢复 tabletop/实际能力按预算。

## 12. Runbooks

```text
docs/runbooks/db-restore.md
object-recovery.md
queue-rebuild.md
agent-run-reconciliation.md
bad-deploy-rollback.md
provider-outage.md
security-incident.md
```

每个包含触发、owner、命令/步骤、验证、退出条件。

## 13. Restore Verification

恢复后自动验证：

```text
schema/migrations
row counts/checksums sample
tenant invariants
object refs
critical projects/artifacts
cost ledger balance
run states
```

## 14. Backup Security

Backup同样敏感：加密、最小权限、删除保护、访问audit。不要把DB dump长期放公共bucket。

## 15. Tests / Drills

至少季度/重大变更后演练；首次上线前必须完成一次真实DB restore和run resume演练。

Source 已提供：

```text
make recovery-postgres-drill
make recovery-object-drill
make recovery-drill
make recovery-db-verify
make recovery-workload
```

注意：本地 drill timing 只能证明恢复机制和测量链路，不能替代 production RPO/RTO 证据。

## 16. 验收标准

- [ ] PostgreSQL PITR/restore验证。
- [ ] Object version/recovery验证。
- [ ] Redis/Broker丢失可重建。
- [ ] AgentRun restart可resume/reconcile。
- [ ] bad deploy rollback runbook实测。
- [ ] RPO/RTO有测量而非宣传。

## 17. Definition of Done

```text
backup policies enabled
+ restore drills passed
+ measured RPO/RTO recorded
+ recovery runbooks approved
```

下一节点：NODE-69 Performance。
