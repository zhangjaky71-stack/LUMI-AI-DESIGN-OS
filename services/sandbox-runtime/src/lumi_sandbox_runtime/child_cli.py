from __future__ import annotations

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


def _execute(payload: dict[str, Any]) -> dict[str, Any]:
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
        work = Path(tmp, "work")
        work.mkdir(mode=0o700)
        try:
            completed = subprocess.run(
                command,
                cwd=work,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout,
                check=False,
                env={
                    "HOME": str(work),
                    "TMPDIR": str(work),
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
    }


def main() -> int:
    bucket = _required_env("LUMI_SANDBOX_EXCHANGE_BUCKET", max_length=255)
    request_key = _required_env("LUMI_SANDBOX_REQUEST_KEY", max_length=1024)
    result_key = _required_env("LUMI_SANDBOX_RESULT_KEY", max_length=1024)
    prefix = "sandbox-exchange/v1/"
    if not request_key.startswith(prefix) or not result_key.startswith(prefix):
        raise SystemExit("sandbox exchange keys must remain inside canonical prefix")
    region = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION")
    s3 = boto3.client("s3", region_name=region)
    try:
        payload = _load_request(s3, bucket, request_key)
        result = _execute(payload)
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
    except (BotoCoreError, ClientError, ChildExecutionError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise SystemExit(f"sandbox child execution failed: {type(exc).__name__}") from exc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
