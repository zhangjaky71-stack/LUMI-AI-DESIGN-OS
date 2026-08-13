# NODE-21 Acceptance — Sandbox Runtime

Status: **IMPLEMENTED / VALIDATING / BLOCKED_EXTERNAL**

## Implementation scope

- [x] Provider-neutral `SandboxBackend` contract.
- [x] Agent-facing `DeepAgentSandboxTools` with no host-exec modules.
- [x] Local/CI Docker backend with fixed argv and `shell=False`.
- [x] Linux root-host execution fails closed instead of producing a root sandbox.
- [x] Read-only root filesystem.
- [x] Docker `network none` default and fail-closed unsupported proxy/allowlist policies.
- [x] All Linux capabilities dropped and `no-new-privileges` enabled.
- [x] CPU, memory, PID, file-descriptor, command-timeout, and writable-disk limits.
- [x] Active commands are bounded by remaining sandbox TTL, not only command timeout.
- [x] `input` read-only bind plus size-limited `work`, `output`, and `/tmp` tmpfs.
- [x] Cumulative trusted Asset input is bounded by a sandbox input quota.
- [x] No Docker socket/home/repository/credential mount.
- [x] Host environment secrets are not inherited.
- [x] Path traversal and canonical symlink-escape checks for file tools.
- [x] Agent file writes are streamed through container stdin as the container user.
- [x] Safe ZIP extraction rejecting traversal/symlink/size/file-count bombs.
- [x] Stream-drained stdout/stderr with return/log caps and secret-pattern redaction.
- [x] Per-exec host staging is removed after execution.
- [x] Per-sandbox retained execution logs have a total host-side budget.
- [x] Local JSONL audit evidence rotates at a hard size budget.
- [x] Output-return budget is constrained relative to sandbox storage budget.
- [x] Stray/background process detection after Agent command completion.
- [x] AssetResolver checksum-bound input port.
- [x] ArtifactSink checksum/MIME output collection port.
- [x] Persistent audit port without user file contents.
- [x] TTL reaper and expired-orphan Docker cleanup support.
- [x] Versioned Python/Node/FFmpeg/ImageMagick/font utility Docker image.
- [x] Effective `docker inspect` hardening proof authored.
- [x] Dependency-light static/unit workflow.
- [x] Frozen-install Ruff/Pyright quality workflow stage.
- [x] Live Docker attack + functional workflow authored.

## Attack cases authored

- [x] `../../` traversal.
- [x] symlink escape to `/etc/passwd`.
- [x] PID exhaustion/fork-style process fanout.
- [x] memory bomb.
- [x] writable-disk fill.
- [x] infinite/long command timeout.
- [x] active execution crossing sandbox TTL.
- [x] cloud metadata IP access.
- [x] Docker socket access.
- [x] host-private environment marker dump attempt.
- [x] oversized stdout.
- [x] cumulative Asset input quota exhaustion.
- [x] ZIP slip and archive symlink.
- [x] actual rootfs write rejection.

## Functional cases authored

- [x] Python execution.
- [x] Node.js execution.
- [x] FFmpeg generation + FFprobe metadata.
- [x] ImageMagick transform.
- [x] Asset input resolution.
- [x] workspace read/write/list.
- [x] file written by Agent tool remains writable by the non-root container user.
- [x] output checksum/MIME collection.
- [x] real backend through Deep Agent adapter.
- [x] per-exec host staging cleanup.
- [x] termination cleanup.
- [x] TTL automatic reaping.

## Hosted evidence

Latest NODE-21 head checked: `c08715c66d773c8680dbcc38201ddd2cdad1cc60`.

`Sandbox Runtime Security` workflow run: **31687134324**.

Observed first job `sandbox-contract`:

```text
job id: 94405715866
conclusion: failure
steps: []
runner_id: 0
runner_name: ""
```

GitHub check annotation:

> The job was not started because recent account payments have failed or your spending limit needs to be increased. Please check the 'Billing & plans' section in your settings.

Therefore this run is **not a product test failure and not a PASS**. The runner never started. `sandbox-quality` and `sandbox-docker-e2e` were skipped because the first job did not execute.

NODE-21 remains **IMPLEMENTED / VALIDATING / BLOCKED_EXTERNAL / not COMPLETE** until `sandbox-contract`, `sandbox-quality`, and `sandbox-docker-e2e` execute on real runners and pass.

## Completion gate

- [ ] Python compile gate PASS on hosted runner.
- [ ] static sandbox security contract PASS on hosted runner.
- [ ] stdlib sandbox unit suite PASS on hosted runner.
- [ ] frozen `uv sync --all-packages --frozen` PASS.
- [ ] targeted Ruff PASS.
- [ ] targeted Pyright PASS.
- [ ] Docker image build PASS.
- [ ] effective Docker hardening inspection PASS.
- [ ] Python/Node/FFmpeg/ImageMagick image smoke PASS.
- [ ] full Docker attack/functional acceptance PASS.
- [ ] no inherited regression in repository gates.
- [x] latest external blocker evidence linked in repository + PR #20.

Next node after green acceptance: **NODE-22 — Model Gateway**.
