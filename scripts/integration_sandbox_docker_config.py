from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from uuid import uuid4

from lumi_sandbox_runtime import DockerSandboxBackend, ExecRequest, SandboxSpec

RUNTIME_ROOT = Path(
    os.getenv("LUMI_SANDBOX_RUNTIME_ROOT", "/tmp/lumi-node21-e2e")
) / "inspect"
IMAGE = os.getenv("LUMI_SANDBOX_IMAGE", "lumi-sandbox:node21-v1")


def main() -> int:
    if os.getenv("LUMI_SANDBOX_DOCKER_E2E") != "1":
        print("NODE-21 Docker config inspection: SKIPPED")
        return 0
    shutil.rmtree(RUNTIME_ROOT, ignore_errors=True)
    backend = DockerSandboxBackend(runtime_root=RUNTIME_ROOT)
    spec = SandboxSpec(
        organization_id=uuid4(),
        agent_run_id=uuid4(),
        image=IMAGE,
        cpu_limit=0.5,
        memory_limit_mb=128,
        disk_limit_mb=64,
        pids_limit=32,
        timeout_seconds=10,
        max_output_bytes=4096,
        ttl_seconds=60,
    )
    sandbox_id = backend.create(spec)
    try:
        lookup = subprocess.run(
            [
                "docker",
                "ps",
                "-q",
                "--filter",
                f"label=lumi.sandbox.id={sandbox_id}",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        container_id = lookup.stdout.strip()
        assert container_id
        inspected = subprocess.run(
            ["docker", "inspect", container_id],
            capture_output=True,
            text=True,
            check=True,
        )
        payload = json.loads(inspected.stdout)[0]
        config = payload["Config"]
        host = payload["HostConfig"]
        user = str(config["User"])
        assert user and user.split(":", 1)[0] != "0", user
        assert host["ReadonlyRootfs"] is True
        assert host["Privileged"] is False
        assert host["NetworkMode"] == "none"
        assert "ALL" in (host.get("CapDrop") or [])
        assert int(host["PidsLimit"]) == 32
        assert int(host["Memory"]) == 128 * 1024 * 1024
        security_opt = host.get("SecurityOpt") or []
        assert any("no-new-privileges" in str(value) for value in security_opt)
        mounts = payload.get("Mounts") or []
        mount_sources = {str(item.get("Source", "")) for item in mounts}
        assert "/var/run/docker.sock" not in mount_sources
        assert "/run/docker.sock" not in mount_sources

        root_write = backend.exec(
            sandbox_id,
            ExecRequest(
                (
                    "python",
                    "-c",
                    "open('/node21-rootfs-probe', 'wb').write(b'x')",
                ),
                timeout_seconds=5,
            ),
        )
        assert root_write.exit_code != 0, root_write
    finally:
        backend.terminate(sandbox_id)
        shutil.rmtree(RUNTIME_ROOT, ignore_errors=True)
    print("NODE-21 effective Docker hardening inspection: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
