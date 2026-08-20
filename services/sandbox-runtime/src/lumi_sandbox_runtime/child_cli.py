from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any
from uuid import UUID

import boto3
from botocore.exceptions import BotoCoreError, ClientError

_MAX_REQUEST_BYTES = 128 * 1024
_MAX_RESULT_BYTES = 64 * 1024 * 1024
_MAX_EXCHANGE_FILE_BYTES = 8 * 1024 * 1024 * 1024
_EXCHANGE_KEY_PREFIX = "sandbox-exchange/v1/"


class ChildExecutionError(RuntimeError):
    pass


def _required_env(name: str, *, max_length: int = 2048) -> str:
    value = os.getenv(name, "")
    if not value or len(value) > max_length or "\x00" in value:
        raise ChildExecutionError(f"{name}_REQUIRED")
    return value


def _load_request(s3: Any, bucket: str, key: str) -> dict[str, Any]:
    response = s3.get_object(Bucket=bucket, Key=key)
    length = response.get("ContentLength")
    if not isinstance(length, int) or length <= 0 or length > _MAX_REQUEST_BYTES:
        raise ChildExecutionError("SANDBOX_CHILD_REQUEST_SIZE_INVALID")
    body = response["Body"].read(_MAX_REQUEST_BYTES + 1)
    if len(body) != length or len(body) > _MAX_REQUEST_BYTES:
        raise ChildExecutionError("SANDBOX_CHILD_REQUEST_SIZE_INVALID")
    payload = json.loads(body.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ChildExecutionError("SANDBOX_CHILD_REQUEST_OBJECT_REQUIRED")
    return payload


def _bounded_text(value: bytes, limit: int) -> tuple[str, bool]:
    truncated = len(value) > limit
    bounded = value[:limit]
    return bounded.decode("utf-8", errors="replace"), truncated


def _exchange_key(value: Any) -> str:
    if (
        not isinstance(value, str)
        or not value.startswith(_EXCHANGE_KEY_PREFIX)
        or len(value) > 1024
        or "\x00" in value
        or "\n" in value
        or "\r" in value
        or "//" in value
        or "/../" in value
        or value.endswith("/..")
    ):
        raise ChildExecutionError("SANDBOX_CHILD_EXCHANGE_KEY_INVALID")
    return value


def _exchange_path(root: Path, value: Any, *, prefix: str) -> Path:
    if (
        not isinstance(value, str)
        or not value.startswith(prefix)
        or value.startswith("/")
        or len(value) > 512
        or "\\" in value
        or "\x00" in value
        or "\n" in value
        or "\r" in value
        or "//" in value
        or "/../" in value
        or value.endswith("/..")
        or value in {prefix.rstrip("/"), ".", ".."}
    ):
        raise ChildExecutionError("SANDBOX_CHILD_EXCHANGE_PATH_INVALID")
    candidate = (root / value).resolve()
    resolved_root = root.resolve()
    try:
        candidate.relative_to(resolved_root)
    except ValueError as exc:
        raise ChildExecutionError("SANDBOX_CHILD_EXCHANGE_PATH_ESCAPE") from exc
    return candidate


def _file_limit(value: Any) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 1 <= value <= _MAX_EXCHANGE_FILE_BYTES
    ):
        raise ChildExecutionError("SANDBOX_CHILD_EXCHANGE_LIMIT_INVALID")
    return value


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _download_exchange_inputs(
    s3: Any,
    bucket: str,
    root: Path,
    raw_inputs: Any,
) -> None:
    if raw_inputs is None:
        return
    if not isinstance(raw_inputs, list) or len(raw_inputs) > 64:
        raise ChildExecutionError("SANDBOX_CHILD_EXCHANGE_INPUTS_INVALID")
    for raw in raw_inputs:
        if not isinstance(raw, dict):
            raise ChildExecutionError("SANDBOX_CHILD_EXCHANGE_INPUT_INVALID")
        key = _exchange_key(raw.get("exchange_key"))
        path = _exchange_path(root, raw.get("path"), prefix="input/")
        max_bytes = _file_limit(raw.get("max_bytes"))
        expected_sha256 = raw.get("expected_sha256")
        if expected_sha256 is not None and (
            not isinstance(expected_sha256, str)
            or len(expected_sha256) != 64
            or any(character not in "0123456789abcdef" for character in expected_sha256)
        ):
            raise ChildExecutionError("SANDBOX_CHILD_EXCHANGE_SHA256_INVALID")
        head = s3.head_object(Bucket=bucket, Key=key)
        size = head.get("ContentLength")
        if not isinstance(size, int) or size < 0 or size > max_bytes:
            raise ChildExecutionError("SANDBOX_CHILD_EXCHANGE_INPUT_SIZE_INVALID")
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        s3.download_file(bucket, key, str(path))
        if not path.is_file() or path.stat().st_size != size:
            raise ChildExecutionError("SANDBOX_CHILD_EXCHANGE_INPUT_SIZE_MISMATCH")
        if expected_sha256 is not None and _sha256_file(path) != expected_sha256:
            raise ChildExecutionError("SANDBOX_CHILD_EXCHANGE_INPUT_CHECKSUM_MISMATCH")
        path.chmod(0o400)


def _upload_exchange_outputs(
    s3: Any,
    bucket: str,
    root: Path,
    raw_outputs: Any,
) -> list[dict[str, Any]]:
    if raw_outputs is None:
        return []
    if not isinstance(raw_outputs, list) or len(raw_outputs) > 16:
        raise ChildExecutionError("SANDBOX_CHILD_EXCHANGE_OUTPUTS_INVALID")
    uploaded: list[dict[str, Any]] = []
    for raw in raw_outputs:
        if not isinstance(raw, dict):
            raise ChildExecutionError("SANDBOX_CHILD_EXCHANGE_OUTPUT_INVALID")
        key = _exchange_key(raw.get("exchange_key"))
        path = _exchange_path(root, raw.get("path"), prefix="output/")
        max_bytes = _file_limit(raw.get("max_bytes"))
        content_type = raw.get("content_type", "application/octet-stream")
        if (
            not isinstance(content_type, str)
            or not content_type
            or len(content_type) > 255
            or "\x00" in content_type
            or "\n" in content_type
            or "\r" in content_type
        ):
            raise ChildExecutionError("SANDBOX_CHILD_EXCHANGE_CONTENT_TYPE_INVALID")
        if not path.is_file() or path.is_symlink():
            raise ChildExecutionError("SANDBOX_CHILD_EXCHANGE_OUTPUT_MISSING")
        size = path.stat().st_size
        if size <= 0 or size > max_bytes:
            raise ChildExecutionError("SANDBOX_CHILD_EXCHANGE_OUTPUT_SIZE_INVALID")
        checksum = _sha256_file(path)
        s3.upload_file(
            str(path),
            bucket,
            key,
            ExtraArgs={
                "ContentType": content_type,
                "Metadata": {"sha256": checksum, "schema-version": "1"},
            },
        )
        uploaded.append(
            {
                "exchange_key": key,
                "path": str(raw.get("path")),
                "size_bytes": size,
                "sha256": checksum,
                "content_type": content_type,
            }
        )
    return uploaded


def _rewrite_command_paths(command: list[str], root: Path) -> list[str]:
    rewritten: list[str] = []
    for part in command:
        if not part.startswith("/sandbox/"):
            rewritten.append(part)
            continue
        relative = part[len("/sandbox/") :]
        if not relative.startswith(("input/", "output/", "work/")):
            raise ChildExecutionError("SANDBOX_CHILD_COMMAND_PATH_INVALID")
        local = _exchange_path(root, relative, prefix=relative.split("/", 1)[0] + "/")
        rewritten.append(str(local))
    return rewritten


def _execute(payload: dict[str, Any], *, s3: Any, bucket: str) -> dict[str, Any]:
    sandbox_id = UUID(str(payload.get("sandbox_id", "")))
    organization_id = UUID(str(payload.get("organization_id", "")))
    agent_run_id = UUID(str(payload.get("agent_run_id", "")))
    command = payload.get("command")
    if (
        not isinstance(command, list)
        or not command
        or len(command) > 128
        or not all(isinstance(item, str) and item and "\x00" not in item for item in command)
    ):
        raise ChildExecutionError("SANDBOX_CHILD_COMMAND_INVALID")
    timeout = payload.get("timeout_seconds")
    max_output = payload.get("max_output_bytes")
    cwd = payload.get("cwd", "work")
    if cwd not in {"work", "input", "output"}:
        raise ChildExecutionError("SANDBOX_CHILD_CWD_INVALID")
    if isinstance(timeout, bool) or not isinstance(timeout, int) or not 1 <= timeout <= 3600:
        raise ChildExecutionError("SANDBOX_CHILD_TIMEOUT_INVALID")
    if (
        isinstance(max_output, bool)
        or not isinstance(max_output, int)
        or not 1024 <= max_output <= _MAX_RESULT_BYTES
    ):
        raise ChildExecutionError("SANDBOX_CHILD_OUTPUT_LIMIT_INVALID")

    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="lumi-sandbox-") as tmp:
        sandbox_root = Path(tmp, "sandbox")
        for directory in ("input", "output", "work"):
            (sandbox_root / directory).mkdir(parents=True, exist_ok=True, mode=0o700)
        _download_exchange_inputs(s3, bucket, sandbox_root, payload.get("exchange_inputs", []))
        rewritten_command = _rewrite_command_paths(command, sandbox_root)
        try:
            completed = subprocess.run(
                rewritten_command,
                cwd=sandbox_root / cwd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout,
                check=False,
                env={
                    "HOME": str(sandbox_root / "work"),
                    "TMPDIR": str(sandbox_root / "work"),
                    "PATH": os.getenv("PATH", "/usr/local/bin:/usr/bin:/bin"),
                    "LANG": "C.UTF-8",
                    "LC_ALL": "C.UTF-8",
                },
            )
            exit_code = int(completed.returncode)
            stdout_raw = completed.stdout
            stderr_raw = completed.stderr
        except subprocess.TimeoutExpired as exc:
            exit_code = 124
            stdout_raw = exc.stdout or b""
            stderr_raw = (exc.stderr or b"") + b"\nSANDBOX_TIMEOUT"
        exchange_outputs: list[dict[str, Any]] = []
        if exit_code == 0:
            exchange_outputs = _upload_exchange_outputs(
                s3,
                bucket,
                sandbox_root,
                payload.get("exchange_outputs", []),
            )

    stdout_limit = max_output // 2
    stderr_limit = max_output - stdout_limit
    stdout, stdout_truncated = _bounded_text(stdout_raw, stdout_limit)
    stderr, stderr_truncated = _bounded_text(stderr_raw, stderr_limit)
    return {
        "schema_version": 1,
        "sandbox_id": str(sandbox_id),
        "organization_id": str(organization_id),
        "agent_run_id": str(agent_run_id),
        "exit_code": exit_code,
        "stdout": stdout,
        "stderr": stderr,
        "stdout_truncated": stdout_truncated,
        "stderr_truncated": stderr_truncated,
        "duration_ms": max(0, int((time.monotonic() - started) * 1000)),
        "exchange_outputs": exchange_outputs,
    }


def main() -> int:
    bucket = _required_env("LUMI_SANDBOX_EXCHANGE_BUCKET", max_length=255)
    request_key = _required_env("LUMI_SANDBOX_REQUEST_KEY", max_length=1024)
    result_key = _required_env("LUMI_SANDBOX_RESULT_KEY", max_length=1024)
    prefix = _EXCHANGE_KEY_PREFIX
    if not request_key.startswith(prefix) or not result_key.startswith(prefix):
        raise SystemExit("sandbox exchange keys must remain inside canonical prefix")
    region = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION")
    s3 = boto3.client("s3", region_name=region)
    try:
        payload = _load_request(s3, bucket, request_key)
        result = _execute(payload, s3=s3, bucket=bucket)
        encoded = json.dumps(result, separators=(",", ":"), sort_keys=True).encode("utf-8")
        if len(encoded) > _MAX_RESULT_BYTES:
            raise ChildExecutionError("SANDBOX_CHILD_RESULT_TOO_LARGE")
        s3.put_object(
            Bucket=bucket,
            Key=result_key,
            Body=encoded,
            ContentType="application/json",
            Metadata={"sandbox-id": result["sandbox_id"], "schema-version": "1"},
        )
    except (
        BotoCoreError,
        ClientError,
        ChildExecutionError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        ValueError,
    ) as exc:
        raise SystemExit(f"sandbox child execution failed: {type(exc).__name__}") from exc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
