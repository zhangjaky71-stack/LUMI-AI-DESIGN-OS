# Sandbox Runtime V1

> NODE-21 / Phase 2 Runtime Foundation  
> Security priority: P0  
> Backend shipped in this node: local/CI Docker backend  
> Production backend: provider-neutral contract; dedicated isolated runtime/provider required

## 1. Security objective

LUMI agents may execute approved Python, Node.js, FFmpeg, ImageMagick and file workflows without receiving direct access to the LUMI host shell, Docker daemon, application database credentials, cloud account credentials, or long-lived model/provider secrets.

The Agent sees only `DeepAgentSandboxTools`. That adapter holds a `SandboxBackend` and a sandbox ID. It does not import `subprocess`, `os`, Docker APIs, or shell helpers.

## 2. SandboxBackend contract

The provider-neutral runtime owns:

```text
create(spec) -> sandbox_id
state(sandbox_id)
exec(sandbox_id, ExecRequest)
read_file(sandbox_id, path)
write_file(sandbox_id, path, bytes)
list_files(sandbox_id, path)
upload_asset(sandbox_id, asset_ref)
collect_artifact(sandbox_id, path)
terminate(sandbox_id)
reap_expired()
```

`AssetResolver`, `ArtifactSink`, and `AuditSink` are ports. Object-storage credentials remain in trusted LUMI services and are not exposed to the sandbox.

## 3. Local / CI Docker backend

`DockerSandboxBackend` invokes Docker only through fixed argv with `shell=False`. Agent-controlled command argv is appended only after `docker exec` and is never interpreted as a host shell command.

Each container is created with:

```text
--network none
--read-only
--cap-drop ALL
--security-opt no-new-privileges:true
--pids-limit <spec>
--memory <spec>
--memory-swap <same-as-memory>
--cpus <spec>
--ulimit nofile=256:256
--user <non-root host uid:gid>
```

On Linux, the local backend refuses to create a sandbox when the host process is UID 0. It fails closed with `SANDBOX_ROOT_HOST_EXECUTION_FORBIDDEN` rather than translating a privileged application process into a root sandbox.

The backend never mounts `/var/run/docker.sock`, user home, repository root, cloud credential directories, database sockets, or application `.env` files.

The runtime image is `lumi-sandbox:node21-v1`, built from `infra/sandbox/Dockerfile` and containing the approved P0 toolset: Python, Node.js, FFmpeg/FFprobe, ImageMagick, zip/unzip, and fontconfig utilities.

## 4. Workspace

The logical workspace is:

```text
/workspace
├── input/   read-only bind mount populated by trusted AssetResolver
├── work/    writable size-limited tmpfs
└── output/  writable size-limited tmpfs
```

`/tmp` is a third size-limited tmpfs. The requested `disk_limit_mb` is divided across work/output/tmp so a command cannot fill the host filesystem through a writable bind mount. `input/` is separately bounded by a cumulative trusted-input quota derived from the same sandbox disk budget.

The base root filesystem remains read-only.

## 5. File boundary

Tool file paths are relative and must start with exactly one of `input`, `work`, or `output`.

Rejected examples:

```text
../../etc/passwd
/etc/passwd
work/../output/file
Windows-style backslash traversal
```

`input` is read-only to Agent file tools.

Before host-side read/write/collect operations, the backend resolves the corresponding path inside the container and verifies that the canonical path stays within its allowed workspace root. A symlink such as:

```text
/workspace/work/escape -> /etc/passwd
```

therefore fails the file-tool boundary instead of being copied back to the host.

Agent `write_file` does not use `docker cp` for the final write. Bytes are streamed over stdin to a fixed in-container Python writer running as the configured non-root container user. This prevents trusted control-plane copy semantics from accidentally producing root-owned Agent workspace files.

A single `write_file` request is additionally capped to the smaller of the sandbox disk budget and 64 MiB. Larger outputs must be generated inside the sandbox and collected from `output/`.

## 6. Command boundary

The sandbox supports argv execution, not host shell strings.

Control-plane commands such as Docker/Podman/nsenter and explicit Docker control paths are rejected by command policy. The primary safety boundary remains the isolated container: read-only root, no capabilities, no Docker socket, no unrestricted network, resource limits, and no host secrets.

A command that leaves background processes alive after returning is treated as a policy violation. The backend checks the container process namespace after each command and fails/kills the sandbox if stray Agent processes remain.

A command timeout kills the container and marks the sandbox `FAILED`; it is not reused after an uncertain process state. Effective command timeout is also bounded by the remaining sandbox TTL, so an active command cannot extend sandbox lifetime.

## 7. Network policy

The contract freezes three policies:

```text
NONE
TOOL_PROXY_ONLY
ALLOWLIST
```

The NODE-21 local/CI backend implements only `NONE`, using Docker `--network none`.

`TOOL_PROXY_ONLY` and `ALLOWLIST` deliberately fail closed in this backend. Production must supply a dedicated egress-enforcing adapter/service. Merely setting `HTTP_PROXY` on a normally connected container is not considered an enforcement boundary.

Allowlist validation rejects loopback, RFC1918, link-local/cloud metadata, `.internal`, `.local`, and Docker host aliases. Production egress must also enforce these boundaries at connection/resolution time rather than trusting only a hostname pre-check.

## 8. Secret model

Host environment variables are not inherited by the container. The backend injects only controlled runtime variables such as `HOME`, `TMPDIR`, and the opaque sandbox ID.

Long-lived model/provider/cloud/database secrets must not be placed in sandbox environment variables.

When a sandbox needs external access, future production adapters must use one of:

- short-lived scoped capability tokens;
- short-lived signed object URLs;
- Tool Gateway / controlled egress proxy.

Command audit records redact common secret argument forms. Returned and persisted logs redact common authorization/token/password patterns. Redaction is defense in depth, not the primary secret boundary.

## 9. Output, staging and log limits

Agent stdout/stderr is drained continuously instead of being accumulated without bound in memory.

- returned stdout/stderr is capped by `max_output_bytes`;
- `max_output_bytes` cannot exceed one quarter of the sandbox disk budget;
- drain threads continue consuming excess output to avoid process pipe deadlock;
- retained execution logs have per-command caps and a per-sandbox total budget;
- per-exec host staging directories are removed after every execution path, including failures;
- local JSONL audit evidence rotates at a hard size budget;
- audit logs and retained execution logs live outside the ephemeral sandbox workspace;
- terminate removes workspace/input/staging data while keeping bounded audit/log evidence.

## 10. Asset input

`upload_asset(asset_ref)` calls a trusted `AssetResolver` outside the sandbox.

The backend:

```text
resolve reference
→ enforce cumulative input quota
→ recompute SHA-256
→ compare expected checksum when present
→ sanitize filename
→ write checksum-prefixed file into input/
→ expose it read-only to the container
```

Repeated uploads of the same checksum-addressed input reuse the existing file rather than consuming quota again. No object-storage credential enters the sandbox.

## 11. Artifact collection

Only regular files under `output/` can be collected.

Collection performs:

```text
canonical path validation
→ Docker copy to trusted staging
→ regular-file check
→ size limit
→ SHA-256
→ magic/header-oriented MIME detection
→ ArtifactSink.store_file(...)
```

Agent-provided filename extensions are not treated as authoritative MIME evidence.

NODE-18 remains the authoritative full Asset validation/storage pipeline. NODE-21 provides the isolated output collection port and checksum/MIME pre-boundary; production wiring should hand collected files into the NODE-18 validation lifecycle rather than bypass it.

## 12. Archive safety

Trusted-side ZIP extraction uses `extract_zip_safely` and rejects:

- absolute members;
- `..` traversal / zip-slip;
- symlink members;
- file-count bombs;
- uncompressed-size bombs.

This prevents a malicious archive from escaping its trusted extraction directory before it ever reaches Agent tooling.

## 13. Lifecycle

Frozen states:

```text
CREATING
READY
RUNNING
IDLE
TERMINATING
TERMINATED
FAILED
```

`SandboxReaper` periodically executes `reap_expired()`. The Docker backend also labels containers with an expiry epoch and can remove expired orphaned containers left by a previous service process.

The public Docker backend can kill an active expired container before waiting on the per-sandbox execution lock. Sandbox workspace persistence ends at termination; durable outputs must be collected first.

## 14. Audit

Audit records contain:

```text
sandbox_id
organization_id
agent_run_id
timestamp
action
state
image
network_policy
sanitized command
exit code
duration
resource reference
small structured detail
```

Audit does not store user file contents.

`JsonlAuditSink` is the NODE-21 bounded local reference sink and retains one rotated segment. Production can replace it with the platform audit/observability adapter without changing Agent tooling.

## 15. Resource limits

`SandboxSpec` freezes:

```text
cpu_limit
memory_limit_mb
disk_limit_mb
pids_limit
timeout_seconds
network_policy
max_output_bytes
ttl_seconds
```

The Docker integration suite attacks each practical local boundary instead of merely checking generated Docker arguments.

## 16. Security acceptance suite

Hosted Docker acceptance executes:

1. workspace `../../` traversal rejection;
2. symlink-to-`/etc/passwd` file-tool escape rejection;
3. PID exhaustion attempt under `--pids-limit`;
4. 512 MiB allocation attempt inside a 96 MiB sandbox;
5. write larger than the writable tmpfs budget;
6. command timeout and failed-sandbox invalidation;
7. active command crossing sandbox TTL;
8. connection attempt to `169.254.169.254` under `network none`;
9. absence of Docker socket;
10. host-private environment marker non-inheritance;
11. 200 KB stdout under a 4 KB return budget;
12. cumulative Asset input quota exhaustion;
13. malicious ZIP traversal and symlink fixtures.

## 17. Functional acceptance suite

Hosted Docker acceptance also proves:

- Python execution;
- Node.js execution;
- FFmpeg generation and FFprobe metadata;
- ImageMagick image transform;
- trusted AssetResolver input;
- read/write/list file tools;
- Agent-written file remains writable by the non-root container user;
- checksum + MIME output collection into an ArtifactSink;
- DeepAgentSandboxTools execution against the real backend;
- per-exec host staging cleanup;
- terminate cleanup;
- TTL automatic termination.

## 18. Production boundary

This node does not claim Docker-on-the-application-host is the final production sandbox architecture.

Production should prefer a separately isolated sandbox service/provider or hardened execution nodes with dedicated egress enforcement and stronger kernel isolation. The `SandboxBackend` contract is intentionally provider-neutral so a future Daytona/Modal/Firecracker/gVisor-class backend can be selected by security/cost benchmark without changing Agent tool semantics.

The local backend must never be made “production capable” by mounting Docker socket into an Agent-accessible container.

## 19. Verification

Dependency-light contract gate:

```bash
make sandbox-contract
```

The dedicated workflow then runs a frozen workspace install plus targeted Ruff and Pyright. Docker attack/functional gate:

```bash
make sandbox-e2e
```

Global Python gates also include the sandbox-runtime tests through the repository test configuration.

## 20. Definition of Done

NODE-21 is complete only when:

```text
sandbox abstraction implemented
+ local Docker backend green
+ static/unit quality gates green
+ escape/resource/network security suite green
+ Deep Agent adapter spike green
+ hosted required gates green
```

After NODE-21: NODE-22 — Model Gateway.
