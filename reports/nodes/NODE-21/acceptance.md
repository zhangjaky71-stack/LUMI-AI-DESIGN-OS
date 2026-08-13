# NODE-21 Acceptance — Sandbox Runtime

Status: **IMPLEMENTED / VALIDATING / BLOCKED_EXTERNAL**

## Implementation scope

- [x] Provider-neutral `SandboxBackend` contract.
- [x] Agent-facing `DeepAgentSandboxTools` with no host-exec modules.
- [x] Local/CI Docker backend with `shell=False` fixed control argv.
- [x] Read-only root filesystem.
- [x] Docker `network none` default and fail-closed unsupported proxy/allowlist policies.
- [x] All Linux capabilities dropped and `no-new-privileges` enabled.
- [x] CPU, memory, PID, file-descriptor, command-timeout, and writable-disk limits.
- [x] `input` read-only bind plus size-limited `work`, `output`, and `/tmp` tmpfs.
- [x] No Docker socket/home/repository/credential mount.
- [x] Host environment secrets are not inherited.
- [x] Path traversal and canonical symlink-escape checks for file tools.
- [x] Safe ZIP extraction rejecting traversal/symlink/size/file-count bombs.
- [x] Stream-drained stdout/stderr with return/log caps and secret-pattern redaction.
- [x] Stray/background process detection after Agent command completion.
- [x] AssetResolver checksum-bound input port.
- [x] ArtifactSink checksum/MIME output collection port.
- [x] Persistent audit port + local JSONL implementation without user file contents.
- [x] TTL reaper and expired-orphan Docker cleanup support.
- [x] Versioned Python/Node/FFmpeg/ImageMagick/font utility Docker image.
- [x] Dependency-light static/unit workflow.
- [x] Live Docker attack + functional workflow authored.

## Attack cases authored

- [x] `../../` traversal.
- [x] symlink escape to `/etc/passwd`.
- [x] PID exhaustion/fork-style process fanout.
- [x] memory bomb.
- [x] writable-disk fill.
- [x] infinite/long command timeout.
- [x] cloud metadata IP access.
- [x] Docker socket access.
- [x] host secret env dump attempt.
- [x] oversized stdout.
- [x] ZIP slip and archive symlink.

## Functional cases authored

- [x] Python execution.
- [x] Node.js execution.
- [x] FFmpeg generation + FFprobe metadata.
- [x] ImageMagick transform.
- [x] Asset input resolution.
- [x] workspace read/write/list.
- [x] output checksum/MIME collection.
- [x] real backend through Deep Agent adapter.
- [x] termination cleanup.
- [x] TTL automatic reaping.

## Evidence status

The code, tests, Dockerfile, security validator, runtime documentation, and hosted acceptance workflow are implemented on the NODE-21 branch.

No hosted PASS is claimed yet. The repository's GitHub Actions runner remains blocked by the previously confirmed account payment / Actions spending-limit condition. A run that never receives a runner is not product validation evidence.

NODE-21 remains **not COMPLETE** until both `sandbox-contract` and `sandbox-docker-e2e` execute on real runners and pass.

## Completion gate

- [ ] Python compile gate PASS.
- [ ] static sandbox security contract PASS.
- [ ] stdlib sandbox unit suite PASS.
- [ ] Docker image build PASS.
- [ ] Python/Node/FFmpeg/ImageMagick image smoke PASS.
- [ ] full Docker attack/functional acceptance PASS.
- [ ] no inherited regression in repository gates.
- [ ] hosted evidence linked here.

Next node after green acceptance: **NODE-22 — Model Gateway**.
