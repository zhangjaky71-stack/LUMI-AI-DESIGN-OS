from __future__ import annotations

import io
import zipfile
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from lumi_sandbox_runtime.agent_tools import SandboxToolset
from lumi_sandbox_runtime.audit import MemoryAuditSink
from lumi_sandbox_runtime.docker_backend import build_docker_run_args
from lumi_sandbox_runtime.models import (
    AssetInputRef,
    CollectedArtifact,
    ExecResult,
    FileEntry,
    NetworkPolicy,
    ResourceUsage,
    SandboxAccessContext,
    SandboxCommand,
    SandboxHandle,
    SandboxSpec,
    SandboxState,
)
from lumi_sandbox_runtime.policy import (
    CommandPolicy,
    SandboxPolicyDenied,
    address_is_blocked,
    validate_allowlist_destination,
    validate_network_policy,
)
from lumi_sandbox_runtime.redaction import SecretRedactor
from lumi_sandbox_runtime.service import SandboxAccessDenied, SandboxRuntimeService
from lumi_sandbox_runtime.workspace import (
    WorkspaceViolation,
    normalize_workspace_path,
    validate_archive_bytes,
)

ORG = UUID("01910000-0000-7000-8000-000000000001")
OTHER_ORG = UUID("01910000-0000-7000-8000-000000000002")
RUN = UUID("01910000-0000-7000-8000-000000000101")
OTHER_RUN = UUID("01910000-0000-7000-8000-000000000102")
NOW = datetime(2026, 8, 16, 10, 30, tzinfo=UTC)


def spec(**overrides):
    values = {
        "organization_id": ORG,
        "agent_run_id": RUN,
        "image": "lumi-sandbox:node21",
        "image_version": "node21-v1",
        "cpu_limit": 1.0,
        "memory_limit_mb": 256,
        "disk_limit_mb": 128,
        "pids_limit": 64,
        "timeout_seconds": 300,
        "command_timeout_seconds": 30,
        "network_policy": NetworkPolicy.NONE,
        "max_output_bytes": 4096,
        "ttl_seconds": 300,
    }
    values.update(overrides)
    return SandboxSpec(**values)


def test_workspace_paths_fail_closed() -> None:
    assert normalize_workspace_path("work/a.txt") == "/workspace/work/a.txt"
    assert normalize_workspace_path("/workspace/output/x.png") == "/workspace/output/x.png"
    for path in (
        "../../etc/passwd",
        "/etc/passwd",
        "work/../../etc/passwd",
        "unknown/file",
        "",
    ):
        with pytest.raises(WorkspaceViolation):
            normalize_workspace_path(path)


def test_zip_slip_is_rejected_before_extraction() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("../escape.txt", "bad")
    with pytest.raises(WorkspaceViolation):
        validate_archive_bytes("evil.zip", buffer.getvalue())


def test_network_policy_blocks_internal_targets_and_requires_real_enforcer() -> None:
    for address in ("127.0.0.1", "169.254.169.254", "10.0.0.8", "192.168.1.4", "::1"):
        assert address_is_blocked(address)
    for destination in (
        "http://127.0.0.1:8080",
        "http://169.254.169.254/latest/meta-data",
        "http://localhost",
        "http://metadata.google.internal",
    ):
        with pytest.raises(SandboxPolicyDenied):
            validate_allowlist_destination(destination)
    allowlisted = spec(
        network_policy=NetworkPolicy.ALLOWLIST,
        network_allowlist=("https://example.com",),
    )
    with pytest.raises(SandboxPolicyDenied, match="real egress enforcement"):
        validate_network_policy(allowlisted, egress_enforcer_available=False)


def test_command_policy_denies_shell_network_tools_and_long_lived_secret_env() -> None:
    policy = CommandPolicy()
    for executable in ("sh", "bash", "curl", "wget", "docker", "nsenter"):
        with pytest.raises(SandboxPolicyDenied):
            policy.validate(SandboxCommand(argv=(executable, "--help")))
    with pytest.raises(SandboxPolicyDenied):
        policy.validate(
            SandboxCommand(argv=("python", "x.py"), env={"OPENAI_API_KEY": "secret"})
        )
    policy.validate(SandboxCommand(argv=("python", "x.py")))
    policy.validate(SandboxCommand(argv=("ffmpeg", "-version")))


def test_docker_run_contract_has_hard_isolation_flags(tmp_path) -> None:
    args = build_docker_run_args(spec(), container_name="lumi-test", input_dir=tmp_path)
    joined = " ".join(args)
    assert "--network none" in joined
    assert "--read-only" in args
    assert "--cap-drop ALL" in joined
    assert "no-new-privileges:true" in args
    assert "--pids-limit 64" in joined
    assert "--cpus 1.0" in joined
    assert "--memory 256m" in joined
    assert "/workspace/input,readonly" in joined
    assert "/workspace/work:rw,nosuid,nodev,size=" in joined
    assert "/workspace/output:rw,nosuid,nodev,size=" in joined
    assert "/var/run/docker.sock" not in joined
    assert "OPENAI_API_KEY" not in joined
    assert "DATABASE_URL" not in joined


def test_secret_redaction_never_relies_on_one_pattern() -> None:
    redactor = SecretRedactor(("canary-secret-123",))
    text = redactor.redact(
        "Authorization: Bearer abc.def.ghi canary-secret-123 sk-test-abcdefghijklmnop AKIAABCDEFGHIJKLMNOP"
    )
    assert "canary-secret-123" not in text
    assert "abc.def.ghi" not in text
    assert "sk-test-" not in text
    assert "AKIAABCDEFGHIJKLMNOP" not in text
    assert text.count("[REDACTED]") >= 4


class FakeBackend:
    def __init__(self) -> None:
        self.handle: SandboxHandle | None = None
        self.files: dict[str, bytes] = {}
        self.exec_calls: list[SandboxCommand] = []

    async def create(self, value: SandboxSpec) -> SandboxHandle:
        self.handle = SandboxHandle(
            sandbox_id="sbx-test",
            organization_id=value.organization_id,
            agent_run_id=value.agent_run_id,
            state=SandboxState.READY,
            image_version=value.image_version,
            created_at=NOW,
            expires_at=NOW + timedelta(seconds=300),
        )
        return self.handle

    async def exec(self, sandbox_id: str, command: SandboxCommand) -> ExecResult:
        self.exec_calls.append(command)
        return ExecResult(
            exit_code=0,
            stdout="ok\n",
            stderr="",
            usage=ResourceUsage(wall_time_ms=1, stdout_bytes=3, stderr_bytes=0),
        )

    async def read_file(self, sandbox_id: str, path: str) -> bytes:
        return self.files[path]

    async def write_file(self, sandbox_id: str, path: str, content: bytes) -> None:
        self.files[path] = content

    async def list_files(self, sandbox_id: str, path: str) -> list[FileEntry]:
        return [FileEntry(path=name, size=len(value)) for name, value in self.files.items()]

    async def upload_asset(self, sandbox_id: str, asset: AssetInputRef) -> str:
        path = f"/workspace/input/{asset.filename}"
        self.files[path] = asset.content
        return path

    async def collect_artifact(self, sandbox_id: str, path: str) -> CollectedArtifact:
        return CollectedArtifact(
            sandbox_id=sandbox_id,
            path=path,
            sha256="a" * 64,
            size=len(self.files.get(path, b"")),
            detected_mime="application/octet-stream",
            storage_ref="asset://candidate/1",
        )

    async def terminate(self, sandbox_id: str) -> None:
        return None


def test_runtime_service_enforces_org_and_agent_run_and_audits() -> None:
    backend = FakeBackend()
    audit = MemoryAuditSink()
    runtime = SandboxRuntimeService(backend, audit)
    context = SandboxAccessContext(organization_id=ORG, agent_run_id=RUN)

    async def scenario() -> None:
        handle = await runtime.create(spec(), context=context)
        assert handle.sandbox_id == "sbx-test"
        result = await runtime.exec(
            handle.sandbox_id,
            SandboxCommand(argv=("python", "x.py")),
            context=context,
        )
        assert result.stdout == "ok\n"
        with pytest.raises(SandboxAccessDenied):
            await runtime.exec(
                handle.sandbox_id,
                SandboxCommand(argv=("python", "x.py")),
                context=SandboxAccessContext(organization_id=OTHER_ORG, agent_run_id=RUN),
            )
        with pytest.raises(SandboxAccessDenied):
            await runtime.exec(
                handle.sandbox_id,
                SandboxCommand(argv=("python", "x.py")),
                context=SandboxAccessContext(organization_id=ORG, agent_run_id=OTHER_RUN),
            )
        assert [event.action.value for event in audit.events][:2] == ["create", "exec"]
        assert audit.events[1].command == ("python", "x.py")

    import asyncio

    asyncio.run(scenario())


def test_deep_agent_toolset_only_targets_sandbox_service() -> None:
    backend = FakeBackend()
    audit = MemoryAuditSink()
    runtime = SandboxRuntimeService(backend, audit)
    context = SandboxAccessContext(organization_id=ORG, agent_run_id=RUN)

    async def scenario() -> None:
        await runtime.create(spec(), context=context)
        tools = SandboxToolset(runtime, sandbox_id="sbx-test", context=context)
        output = await tools.run_python("print('hello')")
        assert output == "ok\n"
        assert backend.exec_calls[-1].argv[0] == "python"
        assert backend.exec_calls[-1].argv[1].startswith("/workspace/work/agent-")
        assert "host_exec" not in dir(tools)
        assert "docker" not in dir(tools)
        assert "shell" not in dir(tools)

    import asyncio

    asyncio.run(scenario())
