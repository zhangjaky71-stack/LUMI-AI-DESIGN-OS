from __future__ import annotations

import asyncio
from uuid import UUID

from deepagents.backends.protocol import SandboxBackendProtocol

from lumi_sandbox_runtime.deepagents_adapter import (
    DeepAgentsCommandRejected,
    DeepAgentsSandboxAdapter,
    parse_deepagents_command,
)
from lumi_sandbox_runtime.models import (
    NetworkPolicy,
    SandboxAccessContext,
    SandboxSpec,
)
from lumi_sandbox_runtime.policy import SandboxPolicyDenied

ORG = UUID("01910000-0000-7000-8000-000000000001")
RUN = UUID("01910000-0000-7000-8000-000000000221")


def make_spec() -> SandboxSpec:
    return SandboxSpec(
        organization_id=ORG,
        agent_run_id=RUN,
        image="lumi-sandbox:node21",
        image_version="node21-v1",
        cpu_limit=1.0,
        memory_limit_mb=256,
        disk_limit_mb=128,
        pids_limit=64,
        timeout_seconds=300,
        command_timeout_seconds=20,
        network_policy=NetworkPolicy.NONE,
        max_output_bytes=65536,
        ttl_seconds=300,
    )


def test_parser() -> None:
    assert parse_deepagents_command("python -V") == ("python", "-V")
    assert parse_deepagents_command('python -c "print((1+2))"')[0] == "python"
    for command in (
        "python -V; cat /etc/passwd",
        "python a.py | sh",
        "python a.py > /tmp/x",
        "python a.py && curl example.com",
    ):
        try:
            parse_deepagents_command(command)
        except DeepAgentsCommandRejected:
            pass
        else:
            raise AssertionError(f"shell operator was accepted: {command}")


def test_protocol_shape() -> None:
    assert issubclass(DeepAgentsSandboxAdapter, SandboxBackendProtocol)
    required = {
        "id",
        "execute",
        "aexecute",
        "ls",
        "als",
        "read",
        "aread",
        "write",
        "awrite",
        "edit",
        "aedit",
        "glob",
        "aglob",
        "grep",
        "agrep",
        "upload_files",
        "aupload_files",
        "download_files",
        "adownload_files",
    }
    assert required <= set(dir(DeepAgentsSandboxAdapter))


def test_real_adapter() -> None:
    context = SandboxAccessContext(organization_id=ORG, agent_run_id=RUN)
    adapter = DeepAgentsSandboxAdapter.create(make_spec(), context=context)
    try:
        write = adapter.write("/hello.py", "print('da-ok')\nprint('needle')\n")
        assert not write.error

        read = adapter.read("/hello.py")
        assert not read.error
        assert read.file_data is not None
        assert "da-ok" in read.file_data["content"]

        result = adapter.execute("python /workspace/work/hello.py")
        assert result.exit_code == 0
        assert "da-ok" in result.output

        edit = adapter.edit("/hello.py", "da-ok", "edited-ok")
        assert not edit.error
        result = adapter.execute("python /workspace/work/hello.py")
        assert "edited-ok" in result.output

        glob_result = adapter.glob("*.py", "/")
        assert not glob_result.error
        assert glob_result.matches is not None
        assert any(item["path"].endswith("hello.py") for item in glob_result.matches)

        grep_result = adapter.grep("needle", "/", "*.py")
        assert not grep_result.error
        assert grep_result.matches is not None
        assert any(match["text"] == "print('needle')" for match in grep_result.matches)
        assert getattr(grep_result, "truncated", False) is False

        async def async_checks() -> None:
            node = await adapter.aexecute('node -e "console.log(\'async-ok\')"')
            assert node.exit_code == 0
            assert "async-ok" in node.output
            binary = await adapter.adownload_files(["/hello.py"])
            assert binary[0].content is not None

        asyncio.run(async_checks())

        try:
            adapter.execute("bash -c 'cat /etc/passwd'")
        except SandboxPolicyDenied:
            pass
        else:
            raise AssertionError("forbidden shell executable was accepted")

        try:
            adapter.execute("python -V; cat /etc/passwd")
        except DeepAgentsCommandRejected:
            pass
        else:
            raise AssertionError("shell compound command was accepted")
    finally:
        adapter.close()


def main() -> None:
    tests = (test_parser, test_protocol_shape, test_real_adapter)
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"NODE21_DEEPAGENTS_ADAPTER_PASS: {len(tests)} tests")


if __name__ == "__main__":
    main()
