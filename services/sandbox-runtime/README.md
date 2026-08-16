# LUMI Sandbox Runtime

NODE-21 provides the isolated execution boundary used by Deep Agents and worker-side file/media tooling.

## V1 capabilities

- tenant + AgentRun scoped `SandboxBackend` abstraction;
- ephemeral Docker Local/CI backend;
- Python, Node.js, FFmpeg, ffprobe and ImageMagick execution;
- CPU/memory/PID/writable-disk/time/output limits;
- default `NetworkPolicy.NONE` with networked modes fail-closed until a real egress enforcer exists;
- `/workspace/input` read-only, `/workspace/work` scratch, `/workspace/output` collected outputs;
- symlink-safe trusted file helper and archive traversal validation;
- output checksum/MIME validation through `ArtifactStoragePort`;
- sanitized audit events;
- Deep Agents `SandboxBackendProtocol` adapter without `LocalShellBackend`.

Agents are never given the Docker socket or a host-shell capability. Production remote isolation, durable audit/storage composition, egress proxy enforcement and signed image supply-chain controls remain explicit follow-up gaps.

Canonical contract: `docs/runtime/SANDBOX-RUNTIME-V1.md`  
Acceptance: `reports/nodes/NODE-21/acceptance.md`
