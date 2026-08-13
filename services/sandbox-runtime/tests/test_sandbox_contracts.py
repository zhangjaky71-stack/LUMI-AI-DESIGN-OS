from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path
from uuid import uuid4

from lumi_sandbox_runtime import (
    DeepAgentSandboxTools,
    ExecResult,
    NetworkPolicy,
    SandboxPathError,
    SandboxSpec,
    UnsafeArchiveError,
    extract_zip_safely,
    normalize_workspace_path,
    validate_allowlist,
)
from lumi_sandbox_runtime.models import CollectedArtifact, FileEntry, SandboxState
from lumi_sandbox_runtime.security import redact_command, redact_text, safe_filename


class _FakeBackend:
    def __init__(self) -> None:
        self.exec_calls = 0
        self.data: dict[str, bytes] = {}

    def exec(self, sandbox_id, request):
        del sandbox_id, request
        self.exec_calls += 1
        return ExecResult(0, "ok", "", False, False, 1, "sandbox-log:test")

    def read_file(self, sandbox_id, path, *, max_bytes=None):
        del sandbox_id, max_bytes
        return self.data[path]

    def write_file(self, sandbox_id, path, data):
        del sandbox_id
        self.data[path] = data

    def list_files(self, sandbox_id, path):
        del sandbox_id
        return (FileEntry(f"{path}/one.txt", "file", 3),)

    def upload_asset(self, sandbox_id, asset_ref):
        del sandbox_id, asset_ref
        return "input/asset.bin"

    def collect_artifact(self, sandbox_id, path):
        return CollectedArtifact(
            artifact_id=uuid4(),
            sandbox_id=sandbox_id,
            source_path=path,
            filename="out.txt",
            size_bytes=3,
            checksum_sha256="0" * 64,
            detected_mime="text/plain",
            storage_ref="asset://test",
        )


class SandboxContractTests(unittest.TestCase):
    def test_spec_defaults_to_no_network_and_validates_limits(self) -> None:
        spec = SandboxSpec(organization_id=uuid4(), agent_run_id=uuid4())
        self.assertEqual(spec.network_policy, NetworkPolicy.NONE)
        with self.assertRaisesRegex(ValueError, "CPU_LIMIT"):
            SandboxSpec(uuid4(), uuid4(), cpu_limit=0.01)
        with self.assertRaisesRegex(ValueError, "ALLOWLIST_REQUIRED"):
            SandboxSpec(uuid4(), uuid4(), network_policy=NetworkPolicy.ALLOWLIST)

    def test_workspace_paths_are_scoped_and_input_is_read_only(self) -> None:
        self.assertEqual(normalize_workspace_path("work/a/b.txt"), ("work", "a/b.txt"))
        for bad in ("../../etc/passwd", "/etc/passwd", "work/../output/x", "work\\x"):
            with self.subTest(path=bad), self.assertRaises(SandboxPathError):
                normalize_workspace_path(bad)
        with self.assertRaisesRegex(SandboxPathError, "READ_ONLY"):
            normalize_workspace_path("input/x", writable=True)

    def test_command_and_log_redaction(self) -> None:
        command = redact_command(("tool", "--api-key", "secret-value", "password=hunter2"))
        self.assertEqual(command[2], "<redacted>")
        self.assertEqual(command[3], "password=<redacted>")
        text = redact_text("Authorization: Bearer abc123 api_key=xyz password=hunter2")
        self.assertNotIn("abc123", text)
        self.assertNotIn("xyz", text)
        self.assertNotIn("hunter2", text)

    def test_allowlist_rejects_internal_and_metadata_targets(self) -> None:
        for bad in (
            "localhost",
            "127.0.0.1",
            "169.254.169.254",
            "10.1.2.3",
            "192.168.1.2",
            "172.16.1.2",
            "metadata.google.internal",
        ):
            with self.subTest(host=bad), self.assertRaises(ValueError):
                validate_allowlist((bad,))
        self.assertEqual(validate_allowlist(("api.example.com",)), ("api.example.com",))

    def test_safe_filename_removes_path_and_control_characters(self) -> None:
        self.assertEqual(safe_filename("../../ weird name?.png"), "weird_name_.png")
        self.assertEqual(safe_filename(".."), "asset.bin")

    def test_zip_slip_and_archive_symlink_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            safe_zip = root / "safe.zip"
            with zipfile.ZipFile(safe_zip, "w") as bundle:
                bundle.writestr("folder/file.txt", "hello")
            extracted = extract_zip_safely(safe_zip, root / "safe")
            self.assertEqual(extracted[0].read_text(encoding="utf-8"), "hello")

            slip_zip = root / "slip.zip"
            with zipfile.ZipFile(slip_zip, "w") as bundle:
                bundle.writestr("../escape.txt", "bad")
            with self.assertRaisesRegex(UnsafeArchiveError, "PATH_TRAVERSAL"):
                extract_zip_safely(slip_zip, root / "slip")

            symlink_zip = root / "symlink.zip"
            link = zipfile.ZipInfo("link")
            link.create_system = 3
            link.external_attr = (0o120777 << 16) | 0xA000
            with zipfile.ZipFile(symlink_zip, "w") as bundle:
                bundle.writestr(link, "/etc/passwd")
            with self.assertRaisesRegex(UnsafeArchiveError, "SYMLINK_FORBIDDEN"):
                extract_zip_safely(symlink_zip, root / "links")

    def test_deep_agent_adapter_exposes_only_sandbox_tools(self) -> None:
        backend = _FakeBackend()
        sandbox_id = uuid4()
        tools = DeepAgentSandboxTools(backend, sandbox_id)
        tools.write_file("work/x.txt", b"abc")
        self.assertEqual(tools.read_file("work/x.txt"), b"abc")
        self.assertEqual(tools.execute(["python", "-V"])["stdout"], "ok")
        self.assertEqual(tools.list_files("work")[0]["kind"], "file")
        self.assertEqual(tools.upload_asset("asset:test"), "input/asset.bin")
        self.assertEqual(tools.collect_artifact("output/out.txt")["storage_ref"], "asset://test")
        self.assertEqual(backend.exec_calls, 1)

    def test_lifecycle_vocabulary_is_frozen(self) -> None:
        self.assertEqual(
            {state.value for state in SandboxState},
            {
                "CREATING",
                "READY",
                "RUNNING",
                "IDLE",
                "TERMINATING",
                "TERMINATED",
                "FAILED",
            },
        )


if __name__ == "__main__":
    unittest.main()
