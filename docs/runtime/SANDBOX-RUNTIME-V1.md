# Sandbox Runtime V1

Status: **FROZEN FOR NODE-21 IMPLEMENTATION**  
Owner: Runtime Foundation / Security  
Depends on: NODE-16, NODE-18, NODE-19  

## 1. Security guarantee

LUMI agents never receive a host shell capability. Untrusted code and media/file tooling run
through `SandboxBackend` and a tenant-scoped `SandboxRuntimeService`. The local/CI reference
backend is an ephemeral Docker container with no host Docker socket, no repository/home/root
mount and no long-lived provider/database/cloud credentials.

This is a defense-in-depth application sandbox, not a claim that ordinary Docker is an ideal
production multi-tenant isolation boundary. Production must use a separately selected remote
sandbox or dedicated strongly isolated execution fleet that implements the same contract.

## 2. Capability boundary

The stable backend contract is:

```text
create(spec) -> SandboxHandle
exec(sandbox_id, SandboxCommand) -> ExecResult
read_file(sandbox_id, path) -> bytes
write_file(sandbox_id, path, bytes)
list_files(sandbox_id, path) -> FileEntry[]
upload_asset(sandbox_id, AssetInputRef) -> workspace path
collect_artifact(sandbox_id, output path) -> CollectedArtifact
terminate(sandbox_id)
```

`SandboxRuntimeService` additionally requires `organization_id + agent_run_id` for every
operation. Possession of a sandbox ID is never sufficient authority. Cross-tenant and
cross-AgentRun access is deliberately indistinguishable from a missing sandbox.

## 3. Workspace

Each sandbox exposes only:

```text
/workspace/input/    read-only imported assets
/workspace/work/     writable scratch
/workspace/output/   writable candidate outputs
```

The host repository, user home, host root and Docker daemon socket are never mounted.

Host-side path checks reject absolute paths outside `/workspace`, NUL, `..`, empty paths and
unknown roots. Container-side trusted file operations use a read-only helper that walks path
components with `openat`/`dir_fd` + `O_NOFOLLOW`, so an agent-created symlink cannot trick a
privileged read/collect operation into following a link outside the permitted subtree.

Archive imports are inspected before exposure. ZIP/TAR members with absolute paths or `..`
components are rejected to prevent zip-slip/tar traversal.

## 4. Local Docker backend hardening

The Local/CI backend creates a fresh container with:

```text
--network none
--read-only
--cap-drop ALL
--security-opt no-new-privileges:true
--pids-limit <spec>
--cpus <spec>
--memory <spec>
--memory-swap == memory
--user 65532:65532
```

Writable scratch is tmpfs-backed and bounded by the sandbox disk budget. `/workspace/input`
is a read-only bind mount from a per-sandbox temporary directory. `/tmp` is a small noexec
scratch tmpfs.

The runtime invokes Docker with `asyncio.create_subprocess_exec`; it never builds a host shell
command and never uses `shell=True`/`create_subprocess_shell`.

## 5. Command policy

Agents execute one approved executable at a time. V1 allows the required design-runtime
programs (`python`, `node`, FFmpeg/ffprobe, ImageMagick, zip/unzip, font utilities) and denies
shells, network clients, SSH tools, Docker/Podman, namespace/mount tools and privilege
escalation utilities.

The Deep Agents adapter accepts its `execute(command: str)` compatibility surface but parses
the command with `shlex`, rejects shell control/redirection operators and forwards an argv
tuple into the same command policy. It does not use Deep Agents `LocalShellBackend` and does
not expose host subprocess handles to the model.

## 6. Deep Agents integration

`DeepAgentsSandboxAdapter` implements `SandboxBackendProtocol` directly. File operations
(read/write/edit/ls/glob/grep/upload/download) map to LUMI workspace APIs rather than shell
one-liners. Sync and async Deep Agents calls are bridged onto one dedicated asyncio loop so
both API styles use the same sandbox lifecycle.

Recursive glob/grep scanning has a bounded entry count and reports truncation when the safety
limit is reached. `grep(max_count=N)` only marks truncation if more than N matches exist.

## 7. Network policy

Network modes are part of `SandboxSpec`:

```text
NONE
TOOL_PROXY_ONLY
ALLOWLIST
```

The Local/CI Docker backend currently enforces only `NONE` using Docker network isolation.
`TOOL_PROXY_ONLY` and `ALLOWLIST` fail closed until a real egress enforcement adapter exists.
LUMI will not substitute an unrestricted bridge network and call it an allowlist.

Any future egress adapter must block loopback, RFC1918, link-local/cloud metadata ranges,
Docker/host internal names and equivalent IPv6 ranges after DNS resolution. Provider/API
access should normally be mediated by Tool Gateway or short-lived scoped credentials.

## 8. Secret policy

Long-lived cloud/provider/database secrets are not injected into sandbox environment
variables. Known secret variable names are denied at the command policy boundary. The base
container environment contains only benign runtime values.

Short-lived access should use one of:

- scoped ephemeral token;
- signed URL;
- Tool Gateway / controlled proxy.

Logs and audit records are redacted for known token patterns and configured canary secrets,
but redaction is a secondary control, not permission to inject secrets in the first place.

## 9. Resource and lifecycle policy

`SandboxSpec` controls CPU, memory, writable disk, PID count, sandbox lifetime, per-command
timeout, network policy and maximum captured output bytes.

stdout/stderr are continuously drained to prevent child-process pipe deadlock but only a
bounded prefix is retained. `ResourceUsage` records observed bytes and whether content was
truncated. A command timeout destroys the entire container so child processes cannot continue
in the background.

TTL and maximum sandbox timeout automatically terminate the sandbox. The Docker backend has a
hard fail-safe expiry; `SandboxRuntimeService` also schedules audited termination. All data
that must outlive the sandbox must first be collected into durable storage.

## 10. Output collection

Only regular files under `/workspace/output` may be collected. The trusted helper validates
the path without following symlinks, measures the file, computes SHA-256 and determines MIME
from known magic signatures before falling back to a filename guess. The agent's declared MIME
is never authoritative.

`ArtifactStoragePort` is the production binding point to NODE-18 storage. The collected record
contains path, checksum, size, detected MIME and optional durable storage reference.

## 11. Audit

Audit events contain:

```text
sandbox_id
organization_id
agent_run_id
action
image_version
network_policy
sanitized command
exit_code
resource usage
path
collected result ref/hash/size/MIME
security denial category
```

Audit never includes full user file contents. `MemoryAuditSink` is the reference sink; durable
production audit composition remains a follow-up integration.

## 12. Required attack evidence

The dedicated NODE-21 gate builds the sandbox image and attempts:

- `../../` traversal;
- symlink escape to `/etc/passwd`;
- PID/fork exhaustion;
- memory exhaustion;
- tmpfs disk fill;
- infinite command timeout;
- cloud metadata IP connection;
- Docker socket discovery;
- cloud/database secret environment enumeration;
- oversized stdout flood;
- malicious ZIP traversal.

Destructive resource tests run in separate sandboxes so one attack cannot invalidate the next
case.

## 13. Functional evidence

The same real Docker harness executes:

- Python file processing;
- Node.js;
- ImageMagick image generation;
- FFmpeg media generation and ffprobe metadata;
- input asset upload;
- safe file read/write/list;
- output validation/checksum/storage-port collection;
- terminate cleanup.

A separate Deep Agents protocol spike imports the exact workspace-locked Deep Agents package,
asserts the protocol shape and exercises synchronous/asynchronous execution plus file APIs.

## 14. Minimal image

`services/sandbox-runtime/docker/Dockerfile` provides the NODE-21 reference image with Python
3.12, Node.js, FFmpeg, ImageMagick, zip/unzip and font tooling under UID/GID 65532. It does not
install cloud CLIs or container administration tools.

The local tag is `lumi-sandbox:node21`. Production deployment still requires a controlled
registry digest, SBOM, vulnerability scan and signed provenance; a mutable upstream base tag
is not treated as a production supply-chain guarantee.

## 15. Packaging boundary

The repository's current frozen `uv.lock` records `lumi-sandbox-runtime` as dependency-free.
NODE-21 therefore does not alter the package dependency declaration without regenerating the
entire reviewed lock. The full workspace already carries Pydantic and Deep Agents dependencies,
which permits the dedicated gate to exercise the implementation, but standalone package
ownership remains an explicit gap rather than a false frozen-lock claim.

## 16. Explicit non-claims

NODE-21 does not claim:

- ordinary Docker is the final production multi-tenant isolation provider;
- `TOOL_PROXY_ONLY` or `ALLOWLIST` egress is active before a real enforcer is installed;
- the output storage port is already wired to production NODE-18 persistence;
- the reference memory audit sink is durable;
- mutable image tags provide production supply-chain provenance;
- hosted security tests passed when GitHub assigned no runner.

Next: **NODE-22 — Model Gateway**.
