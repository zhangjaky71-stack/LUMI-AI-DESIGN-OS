from __future__ import annotations

import asyncio
import io
import json
import zipfile
from uuid import UUID, uuid4

from lumi_sandbox_runtime import (
    AssetInputRef,
    DockerSandboxBackend,
    NetworkPolicy,
    SandboxCommand,
    SandboxNotFound,
    SandboxPolicyDenied,
    SandboxSpec,
)

ORG = UUID("01910000-0000-7000-8000-000000000001")
RUN = UUID("01910000-0000-7000-8000-000000000201")
IMAGE = "lumi-sandbox:node21"


class MemoryStorage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    async def put_validated_output(
        self,
        *,
        organization_id: str,
        sandbox_id: str,
        path: str,
        content: bytes,
        sha256: str,
        detected_mime: str,
    ) -> str:
        key = f"memory://{organization_id}/{sandbox_id}/{sha256}"
        self.objects[key] = bytes(content)
        return key


def make_spec(**overrides) -> SandboxSpec:
    values = {
        "organization_id": ORG,
        "agent_run_id": RUN,
        "image": IMAGE,
        "image_version": "node21-v1",
        "cpu_limit": 1.0,
        "memory_limit_mb": 256,
        "disk_limit_mb": 128,
        "pids_limit": 64,
        "timeout_seconds": 300,
        "command_timeout_seconds": 10,
        "network_policy": NetworkPolicy.NONE,
        "max_output_bytes": 4096,
        "ttl_seconds": 300,
    }
    values.update(overrides)
    return SandboxSpec(**values)


async def docker_json(*args: str):
    process = await asyncio.create_subprocess_exec(
        "docker",
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    if process.returncode != 0:
        raise AssertionError(stderr.decode("utf-8", "replace"))
    return json.loads(stdout.decode("utf-8"))


async def assert_runtime_hardening(container_name: str) -> None:
    data = await docker_json("inspect", container_name)
    assert len(data) == 1
    item = data[0]
    host = item["HostConfig"]
    assert host["NetworkMode"] == "none"
    assert host["ReadonlyRootfs"] is True
    assert host["Memory"] == 256 * 1024 * 1024
    assert host["MemorySwap"] == 256 * 1024 * 1024
    assert host["PidsLimit"] == 64
    assert host["NanoCpus"] == 1_000_000_000
    assert "ALL" in (host.get("CapDrop") or [])
    assert any("no-new-privileges" in value for value in host.get("SecurityOpt") or [])
    mounts = item.get("Mounts") or []
    assert all(mount.get("Destination") != "/var/run/docker.sock" for mount in mounts)
    tmpfs = host.get("Tmpfs") or {}
    assert "/workspace/work" in tmpfs
    assert "/workspace/output" in tmpfs


async def functional_and_escape_suite() -> None:
    storage = MemoryStorage()
    backend = DockerSandboxBackend(storage=storage)
    handle = await backend.create(make_spec())
    name = f"lumi-{handle.sandbox_id}"
    try:
        await assert_runtime_hardening(name)

        asset = AssetInputRef(
            asset_id=uuid4(),
            filename="input.txt",
            content=b"hello sandbox",
            declared_mime="text/plain",
        )
        path = await backend.upload_asset(handle.sandbox_id, asset)
        assert path == "/workspace/input/input.txt"

        result = await backend.exec(
            handle.sandbox_id,
            SandboxCommand(
                argv=(
                    "python",
                    "-c",
                    "from pathlib import Path; p=Path('/workspace/input/input.txt').read_text(); Path('/workspace/output/result.txt').write_text(p.upper()); print(p)",
                )
            ),
        )
        assert result.exit_code == 0 and "hello sandbox" in result.stdout
        assert await backend.read_file(handle.sandbox_id, "/workspace/output/result.txt") == b"HELLO SANDBOX"

        node = await backend.exec(
            handle.sandbox_id,
            SandboxCommand(argv=("node", "-e", "console.log('node-ok')")),
        )
        assert node.exit_code == 0 and "node-ok" in node.stdout

        image = await backend.exec(
            handle.sandbox_id,
            SandboxCommand(
                argv=("convert", "-size", "16x16", "xc:red", "/workspace/output/red.png")
            ),
        )
        assert image.exit_code == 0
        artifact = await backend.collect_artifact(handle.sandbox_id, "/workspace/output/red.png")
        assert artifact.detected_mime == "image/png"
        assert artifact.storage_ref is not None
        assert storage.objects[artifact.storage_ref].startswith(b"\x89PNG")

        video = await backend.exec(
            handle.sandbox_id,
            SandboxCommand(
                argv=(
                    "ffmpeg",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-f",
                    "lavfi",
                    "-i",
                    "color=c=blue:s=16x16:d=0.2",
                    "-c:v",
                    "mpeg4",
                    "-y",
                    "/workspace/output/clip.mp4",
                ),
                timeout_seconds=10,
            ),
        )
        assert video.exit_code == 0
        probe = await backend.exec(
            handle.sandbox_id,
            SandboxCommand(
                argv=(
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=format_name",
                    "-of",
                    "default=nw=1",
                    "/workspace/output/clip.mp4",
                )
            ),
        )
        assert probe.exit_code == 0 and "format_name" in probe.stdout

        try:
            await backend.read_file(handle.sandbox_id, "../../etc/passwd")
        except Exception:
            pass
        else:
            raise AssertionError("path traversal was not rejected")

        symlink = await backend.exec(
            handle.sandbox_id,
            SandboxCommand(
                argv=(
                    "python",
                    "-c",
                    "import os; os.symlink('/etc/passwd','/workspace/work/leak')",
                )
            ),
        )
        assert symlink.exit_code == 0
        try:
            await backend.read_file(handle.sandbox_id, "/workspace/work/leak")
        except SandboxPolicyDenied:
            pass
        else:
            raise AssertionError("symlink escape was not rejected")

        network = await backend.exec(
            handle.sandbox_id,
            SandboxCommand(
                argv=(
                    "python",
                    "-c",
                    "import socket\ntry:\n socket.create_connection(('169.254.169.254',80),1); print('OPEN')\nexcept OSError:\n print('BLOCKED')",
                )
            ),
        )
        assert "BLOCKED" in network.stdout and "OPEN" not in network.stdout

        socket_check = await backend.exec(
            handle.sandbox_id,
            SandboxCommand(
                argv=(
                    "python",
                    "-c",
                    "import os; print(os.path.exists('/var/run/docker.sock'))",
                )
            ),
        )
        assert socket_check.stdout.strip() == "False"

        env_check = await backend.exec(
            handle.sandbox_id,
            SandboxCommand(
                argv=(
                    "python",
                    "-c",
                    "import os; print([k for k in os.environ if k.startswith(('AWS_','AZURE_','GOOGLE_')) or k in {'OPENAI_API_KEY','ANTHROPIC_API_KEY','DATABASE_URL','PGPASSWORD','DOCKER_HOST'}])",
                )
            ),
        )
        assert env_check.stdout.strip() == "[]"

        flood = await backend.exec(
            handle.sandbox_id,
            SandboxCommand(argv=("python", "-c", "print('x'*100000)")),
        )
        assert flood.usage.output_truncated is True
        assert len(flood.stdout.encode("utf-8")) <= 4096

        evil = io.BytesIO()
        with zipfile.ZipFile(evil, "w") as archive:
            archive.writestr("../outside.txt", "owned")
        try:
            await backend.upload_asset(
                handle.sandbox_id,
                AssetInputRef(
                    asset_id=uuid4(),
                    filename="evil.zip",
                    content=evil.getvalue(),
                ),
            )
        except Exception:
            pass
        else:
            raise AssertionError("zip-slip archive was accepted")
    finally:
        await backend.terminate(handle.sandbox_id)

    try:
        await backend.exec(handle.sandbox_id, SandboxCommand(argv=("python", "-V")))
    except SandboxNotFound:
        pass
    else:
        raise AssertionError("terminated sandbox remained executable")


async def pid_limit_suite() -> None:
    backend = DockerSandboxBackend()
    handle = await backend.create(make_spec(pids_limit=24))
    try:
        result = await backend.exec(
            handle.sandbox_id,
            SandboxCommand(
                argv=(
                    "python",
                    "-c",
                    "import subprocess\nps=[]\nfor i in range(60):\n try: ps.append(subprocess.Popen(['python','-c','import time;time.sleep(10)']))\n except OSError: break\nprint(len(ps))\nfor p in ps: p.terminate()",
                ),
                timeout_seconds=10,
            ),
        )
        count = int(result.stdout.strip().splitlines()[-1])
        assert count < 60
    finally:
        await backend.terminate(handle.sandbox_id)


async def memory_limit_suite() -> None:
    backend = DockerSandboxBackend()
    handle = await backend.create(make_spec(memory_limit_mb=128))
    try:
        result = await backend.exec(
            handle.sandbox_id,
            SandboxCommand(
                argv=(
                    "python",
                    "-c",
                    "x=bytearray(512*1024*1024); print(len(x))",
                ),
                timeout_seconds=10,
            ),
        )
        assert result.exit_code != 0 or "MemoryError" in result.stderr
    finally:
        await backend.terminate(handle.sandbox_id)


async def disk_limit_suite() -> None:
    backend = DockerSandboxBackend()
    handle = await backend.create(make_spec(disk_limit_mb=64))
    try:
        result = await backend.exec(
            handle.sandbox_id,
            SandboxCommand(
                argv=(
                    "python",
                    "-c",
                    "p=open('/workspace/output/fill.bin','wb')\ntry:\n [p.write(b'x'*1024*1024) for _ in range(100)]; print('OPEN')\nexcept OSError:\n print('BLOCKED')\nfinally:\n p.close()",
                ),
                timeout_seconds=10,
            ),
        )
        assert "BLOCKED" in result.stdout and "OPEN" not in result.stdout
    finally:
        await backend.terminate(handle.sandbox_id)


async def timeout_suite() -> None:
    backend = DockerSandboxBackend()
    handle = await backend.create(make_spec(command_timeout_seconds=1))
    result = await backend.exec(
        handle.sandbox_id,
        SandboxCommand(argv=("python", "-c", "import time; time.sleep(30)"), timeout_seconds=1),
    )
    assert result.timed_out is True
    assert result.exit_code == 124
    await backend.terminate(handle.sandbox_id)


async def main() -> None:
    suites = (
        functional_and_escape_suite,
        pid_limit_suite,
        memory_limit_suite,
        disk_limit_suite,
        timeout_suite,
    )
    for suite in suites:
        await suite()
        print(f"PASS {suite.__name__}")
    print(f"NODE21_DOCKER_SANDBOX_PASS: {len(suites)} suites")


if __name__ == "__main__":
    asyncio.run(main())
