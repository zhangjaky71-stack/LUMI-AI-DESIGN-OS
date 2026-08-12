# NODE-21 — Sandbox Runtime

> Phase: 2 Runtime Foundation  
> Status: SPECIFIED / READY FOR IMPLEMENTATION  
> Priority: P0 / SECURITY  
> Depends on: NODE-16, NODE-18, NODE-19  
> Produces: Agent 隔离执行抽象、本地 sandbox backend、资源/网络/文件权限与审计

---

## 1. 目标

让 Deep Agents 可以安全执行 Python/Node/FFmpeg/ImageMagick/文件操作，而不能直接获得 LUMI host shell、数据库密码或云账号长期 Secret。

Deep Agents 支持可插拔 filesystem/sandbox backend；LUMI 在其上增加 tenant、resource、egress 和 audit policy。

## 2. SandboxBackend Contract

```text
create(spec) -> sandbox_id
exec(command, cwd, timeout)
read_file(path)
write_file(path, bytes/ref)
list_files(path)
upload_asset(asset_ref)
collect_artifact(path)
terminate()
```

Agent 只看到受限 tool，不知道底层是 Docker/remote provider。

## 3. Backends

### Local / CI

Ephemeral Docker container backend。

### Production

优先独立远程 sandbox service/provider 或强隔离容器节点；保留 Daytona/Modal/其他符合需求 provider adapter 可能性。具体生产 provider 在部署阶段基于安全/成本 benchmark 选择。

禁止把 `/var/run/docker.sock` 直接给 Agent container。

## 4. Workspace

每个 sandbox：

```text
/workspace
├─ input/     read-only copied/scoped
├─ work/      read-write
└─ output/    collected results
```

不能挂载整个 repo、用户 home、host root。

## 5. Base Image

建立版本化 minimal image，包含经过批准的：

```text
Python
Node.js
FFmpeg
ImageMagick
basic image libs
zip/unzip
font utilities
```

不默认包含 cloud CLI credentials。

## 6. Resource Limits

SandboxSpec：

```text
cpu_limit
memory_limit_mb
disk_limit_mb
pids_limit
timeout_seconds
network_policy
max_output_bytes
```

命令 stdout/stderr 截断 + full log 受控存储，防止 context flood。

## 7. Network Policy

默认 deny unrestricted egress。

允许模式：

```text
NONE
TOOL_PROXY_ONLY
ALLOWLIST
```

Agent 访问互联网首选 Tool Gateway/HTTP proxy；避免任意 curl 到 metadata/internal network。

必须阻断 cloud metadata IP、loopback/internal RFC1918（除受控服务）、Docker daemon 等。

## 8. Secret Injection

长期 provider key 不进入 sandbox env。

必要访问通过：

- short-lived scoped token；
- signed URL；
- Tool Gateway proxy。

命令日志进行 secret redaction，但 redaction 不是泄漏后的唯一防线。

## 9. File Permissions

防 path traversal/symlink escape：所有 file operations canonicalize path，必须在 workspace root 内。

禁止读取 `/etc/passwd` 等 host path；container 自身系统文件也按 tool policy 限制。

## 10. Output Collection

Agent 标记 output path；Sandbox service：

```text
validate file
→ checksum
→ upload Object Storage
→ create Asset/Artifact candidate ref
```

不直接信任 Agent 声称 MIME。

## 11. Lifecycle

```text
CREATING
READY
RUNNING
IDLE
TERMINATING
TERMINATED
FAILED
```

TTL 到期自动 terminate；项目文件需要持久化必须先 collect 到 Object Storage/Memory backend。

## 12. Audit

记录：

```text
sandbox_id
agent_run_id
organization_id
image_version
commands (sanitized)
exit code
time/resources
network policy
collected outputs
```

不要把用户文件内容全文写审计。

## 13. Security Tests

必须攻击性测试：

- `../../` traversal；
- symlink escape；
- fork bomb/PID limit；
- memory bomb；
- disk fill；
- infinite command timeout；
- metadata IP access；
- host Docker socket；
- secret env dump；
- oversized stdout；
- malicious archive zip-slip。

## 14. Functional Tests

- execute Python；
- execute Node；
- ffmpeg metadata；
- ImageMagick transform；
- upload input asset；
- collect output；
- terminate cleanup。

## 15. 验收标准

- [ ] Agent 不能直接 host exec。
- [ ] Local sandbox 可创建/运行/销毁。
- [ ] CPU/memory/time/PID limits 生效。
- [ ] workspace traversal 失败。
- [ ] default unrestricted egress 被拒绝。
- [ ] 长期 provider secret 不注入 sandbox。
- [ ] output 经验证后进入 storage。
- [ ] sandbox action 可审计。

## 16. Definition of Done

```text
sandbox abstraction implemented
+ local backend green
+ escape/limit security suite green
+ Deep Agents backend integration spike green
```

完成 Phase 2，下一节点：NODE-22 Model Gateway。
