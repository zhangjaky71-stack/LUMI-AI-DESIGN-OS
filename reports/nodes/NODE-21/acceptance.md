# NODE-21 — Sandbox Runtime Acceptance

Status: **IMPLEMENTED / VALIDATING**  
Hosted status: **not PASS until a runner actually executes the workflow**

## Implemented

- `SandboxBackend` abstraction and tenant/AgentRun-scoped runtime service;
- ephemeral Local/CI Docker backend with no host shell API exposed to agents;
- read-only rootfs, non-root UID/GID, all Linux capabilities dropped and no-new-privileges;
- CPU, memory, PID, writable tmpfs disk, command timeout, sandbox TTL and output limits;
- enforced local `NetworkPolicy.NONE`; proxy/allowlist modes fail closed without an enforcer;
- blocked metadata/internal/loopback address policy for future egress adapters;
- command executable allowlist plus shell/network/container-admin denylist;
- long-lived cloud/provider/database secret environment deny policy;
- bounded/redacted stdout/stderr collection;
- input/read-write/output workspace separation;
- trusted `O_NOFOLLOW`/`dir_fd` workspace helper for symlink-safe reads/writes/collection;
- ZIP/TAR traversal validation;
- validated output SHA-256 and MIME detection plus `ArtifactStoragePort`;
- structured sanitized audit contract and audited lifecycle service;
- Deep Agents capability toolset and direct `SandboxBackendProtocol` adapter;
- versioned NODE-21 minimal execution image;
- seven JSON Schema exports;
- real Docker functional + attack harness;
- exact locked Deep Agents protocol compatibility spike.

## Security evidence committed

The Docker harness validates or attacks:

1. real container `network=none`;
2. read-only root filesystem;
3. memory+swap limit;
4. CPU quota;
5. PID limit;
6. dropped capabilities + no-new-privileges;
7. no `/var/run/docker.sock` mount;
8. bounded tmpfs work/output;
9. `../../` traversal rejection;
10. symlink `/workspace/work/leak -> /etc/passwd` cannot be read by trusted file API;
11. cloud metadata IP cannot be reached;
12. known provider/cloud/database secrets are absent from environment;
13. oversized stdout is truncated while the process pipe is drained;
14. malicious ZIP traversal is rejected before exposure;
15. PID exhaustion is constrained;
16. memory bomb fails under cgroup limit;
17. output disk fill fails under tmpfs limit;
18. infinite command is terminated and the sandbox destroyed;
19. terminated sandbox cannot execute again.

## Functional evidence committed

- Python reads a mounted input and writes output;
- Node.js executes;
- ImageMagick creates PNG output;
- FFmpeg creates media and ffprobe reads metadata;
- input Asset is uploaded read-only;
- trusted helper reads and lists output;
- output collection validates type/hash and sends bytes through storage port;
- Deep Agents sync execute/read/write/edit/glob/grep;
- Deep Agents async Node execute/download;
- compound shell syntax and `bash` are rejected.

## Canonical source checks

```bash
uv sync --all-packages --frozen
PYTHONPATH=services/sandbox-runtime/src uv run python tools/node21/validate_sandbox_runtime.py
PYTHONPATH=services/sandbox-runtime/src uv run pytest -q services/sandbox-runtime/tests/test_sandbox_contract.py
PYTHONPATH=services/sandbox-runtime/src uv run python tools/node21/export_sandbox_schemas.py
uv run ruff check services/sandbox-runtime/src services/sandbox-runtime/tests tools/node21
uv run pyright services/sandbox-runtime/src services/sandbox-runtime/tests tools/node21
```

Hosted workflow must additionally:

```text
build lumi-sandbox:node21
inspect image user/env/helper
run real Docker attack/functional harness
run exact workspace-locked Deep Agents protocol adapter spike
assert no labeled LUMI sandbox containers remain afterward
capture Docker diagnostics on failure
```

## Evidence required before COMPLETE

- Python 3.12 frozen workspace install green;
- static security validator green;
- unit contract suite green;
- seven JSON Schemas parse green;
- Ruff green;
- Pyright green;
- real Docker functional suite green;
- real Docker escape/resource attack suite green;
- exact locked Deep Agents integration spike green;
- repository CI/security gates green;
- stacked NODE-09 through NODE-20 dependencies resolved;
- production gaps closed or explicitly reassigned to their owning later nodes.

## Explicit open gaps

See `reports/nodes/NODE-21/gap-ledger.json`. Notably:

- standalone package dependency ownership is not yet reflected in `uv.lock`;
- Local Docker only activates network NONE;
- production NODE-18 storage adapter is not composed;
- final remote/strong-isolation production backend is not selected;
- durable audit/observability is not composed;
- production image digest/SBOM/signing is not complete;
- GitHub hosted validation is externally blocked by billing/spending limit.

## Explicit non-claims

- no production multi-tenant isolation PASS from ordinary Docker alone;
- no unrestricted or pretend-allowlisted egress;
- no long-lived provider secret availability inside sandboxes;
- no production remote provider PASS;
- no hosted PASS when the workflow job has `runner_id=0` and `steps=[]`.

## Completion rule

A GitHub job that never receives a runner is `BLOCKED_EXTERNAL`, not a source failure and not a PASS.

Next: **NODE-22 — Model Gateway**.
