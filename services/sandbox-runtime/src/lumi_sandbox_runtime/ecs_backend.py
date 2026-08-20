from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

import boto3
from botocore.exceptions import BotoCoreError, ClientError, WaiterError

from .models import CollectedArtifact, ExecRequest, ExecResult, FileEntry, SandboxSpec, SandboxState

_MAX_EXCHANGE_BYTES = 64 * 1024 * 1024


class ECSRemoteSandboxError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class _SandboxRecord:
    spec: SandboxSpec
    state: SandboxState


class ECSRemoteSandboxBackend:
    """Remote Fargate backend; user commands never run inside the hosted API task."""

    def __init__(
        self,
        *,
        cluster: str,
        task_definition: str,
        container: str,
        subnets: tuple[str, ...],
        security_groups: tuple[str, ...],
        exchange_bucket: str,
        region: str | None = None,
    ) -> None:
        if not cluster or not task_definition or not container:
            raise ValueError("SANDBOX_ECS_RUNTIME_IDENTITY_REQUIRED")
        if not subnets or not security_groups:
            raise ValueError("SANDBOX_ECS_PRIVATE_NETWORK_REQUIRED")
        if not exchange_bucket or "/" in exchange_bucket:
            raise ValueError("SANDBOX_EXCHANGE_BUCKET_INVALID")
        self._cluster = cluster
        self._task_definition = task_definition
        self._container = container
        self._subnets = subnets
        self._security_groups = security_groups
        self._bucket = exchange_bucket
        self._ecs = boto3.client("ecs", region_name=region)
        self._s3 = boto3.client("s3", region_name=region)
        self._lock = threading.Lock()
        self._sandboxes: dict[UUID, _SandboxRecord] = {}

    @classmethod
    def from_env(cls) -> "ECSRemoteSandboxBackend":
        region = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION")
        return cls(
            cluster=_required_env("LUMI_SANDBOX_CHILD_CLUSTER"),
            task_definition=_required_env("LUMI_SANDBOX_CHILD_TASK_DEFINITION"),
            container=_required_env("LUMI_SANDBOX_CHILD_CONTAINER"),
            subnets=_csv_env("LUMI_SANDBOX_CHILD_SUBNETS"),
            security_groups=_csv_env("LUMI_SANDBOX_CHILD_SECURITY_GROUPS"),
            exchange_bucket=_required_env("LUMI_SANDBOX_EXCHANGE_BUCKET", max_length=255),
            region=region,
        )

    def create(self, spec: SandboxSpec) -> UUID:
        if spec.network_policy.value != "NONE":
            raise ECSRemoteSandboxError("SANDBOX_REMOTE_NETWORK_POLICY_UNSUPPORTED")
        sandbox_id = uuid4()
        with self._lock:
            self._sandboxes[sandbox_id] = _SandboxRecord(spec=spec, state=SandboxState.READY)
        return sandbox_id

    def state(self, sandbox_id: UUID) -> SandboxState:
        with self._lock:
            record = self._sandboxes.get(sandbox_id)
        return record.state if record is not None else SandboxState.TERMINATED

    def exec(self, sandbox_id: UUID, request: ExecRequest) -> ExecResult:
        with self._lock:
            record = self._sandboxes.get(sandbox_id)
            if record is None or record.state not in {SandboxState.READY, SandboxState.IDLE}:
                raise ECSRemoteSandboxError("SANDBOX_NOT_READY")
            self._sandboxes[sandbox_id] = _SandboxRecord(record.spec, SandboxState.RUNNING)
        spec = record.spec
        operation_id = uuid4()
        prefix = (
            f"sandbox-exchange/v1/{spec.organization_id}/{spec.agent_run_id}/"
            f"{sandbox_id}/{operation_id}"
        )
        request_key = f"{prefix}/request.json"
        result_key = f"{prefix}/result.json"
        payload = {
            "schema_version": 1,
            "sandbox_id": str(sandbox_id),
            "organization_id": str(spec.organization_id),
            "agent_run_id": str(spec.agent_run_id),
            "command": list(request.command),
            "timeout_seconds": request.timeout_seconds or spec.timeout_seconds,
            "max_output_bytes": spec.max_output_bytes,
        }
        encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        if len(encoded) > 128 * 1024:
            raise ECSRemoteSandboxError("SANDBOX_REMOTE_REQUEST_TOO_LARGE")

        task_arn: str | None = None
        try:
            self._s3.put_object(
                Bucket=self._bucket,
                Key=request_key,
                Body=encoded,
                ContentType="application/json",
                Metadata={"sandbox-id": str(sandbox_id), "schema-version": "1"},
            )
            task_arn = self._start_child(request_key=request_key, result_key=result_key)
            self._wait_child(task_arn, timeout_seconds=payload["timeout_seconds"])
            result = self._read_result(result_key, sandbox_id=sandbox_id)
            with self._lock:
                if sandbox_id in self._sandboxes:
                    self._sandboxes[sandbox_id] = _SandboxRecord(spec, SandboxState.IDLE)
            return ExecResult(
                exit_code=result["exit_code"],
                stdout=result["stdout"],
                stderr=result["stderr"],
                stdout_truncated=result["stdout_truncated"],
                stderr_truncated=result["stderr_truncated"],
                duration_ms=result["duration_ms"],
                log_ref=f"sandbox-log://{sandbox_id}/{operation_id}",
            )
        except (BotoCoreError, ClientError, WaiterError, ECSRemoteSandboxError) as exc:
            with self._lock:
                if sandbox_id in self._sandboxes:
                    self._sandboxes[sandbox_id] = _SandboxRecord(spec, SandboxState.FAILED)
            raise ECSRemoteSandboxError("SANDBOX_REMOTE_EXECUTION_FAILED") from exc
        finally:
            try:
                self._s3.delete_object(Bucket=self._bucket, Key=request_key)
            except (BotoCoreError, ClientError):
                pass

    def _start_child(self, *, request_key: str, result_key: str) -> str:
        response = self._ecs.run_task(
            cluster=self._cluster,
            taskDefinition=self._task_definition,
            launchType="FARGATE",
            count=1,
            networkConfiguration={
                "awsvpcConfiguration": {
                    "subnets": list(self._subnets),
                    "securityGroups": list(self._security_groups),
                    "assignPublicIp": "DISABLED",
                }
            },
            overrides={
                "containerOverrides": [
                    {
                        "name": self._container,
                        "environment": [
                            {"name": "LUMI_SANDBOX_REQUEST_KEY", "value": request_key},
                            {"name": "LUMI_SANDBOX_RESULT_KEY", "value": result_key},
                        ],
                    }
                ]
            },
            startedBy=f"lumi-sandbox-{uuid4().hex}"[:36],
        )
        failures = response.get("failures", [])
        if failures:
            raise ECSRemoteSandboxError("SANDBOX_ECS_RUN_TASK_FAILED")
        tasks = response.get("tasks", [])
        if len(tasks) != 1 or not isinstance(tasks[0], dict):
            raise ECSRemoteSandboxError("SANDBOX_ECS_TASK_MISSING")
        task_arn = tasks[0].get("taskArn")
        if not isinstance(task_arn, str) or not task_arn:
            raise ECSRemoteSandboxError("SANDBOX_ECS_TASK_ARN_MISSING")
        return task_arn

    def _wait_child(self, task_arn: str, *, timeout_seconds: int) -> None:
        attempts = max(10, min(620, (timeout_seconds + 120) // 5 + 1))
        self._ecs.get_waiter("tasks_stopped").wait(
            cluster=self._cluster,
            tasks=[task_arn],
            WaiterConfig={"Delay": 5, "MaxAttempts": attempts},
        )
        response = self._ecs.describe_tasks(cluster=self._cluster, tasks=[task_arn])
        tasks = response.get("tasks", [])
        if len(tasks) != 1 or not isinstance(tasks[0], dict):
            raise ECSRemoteSandboxError("SANDBOX_ECS_STOPPED_TASK_MISSING")
        containers = tasks[0].get("containers", [])
        matches = [
            item
            for item in containers
            if isinstance(item, dict) and item.get("name") == self._container
        ]
        if len(matches) != 1 or matches[0].get("exitCode") != 0:
            raise ECSRemoteSandboxError("SANDBOX_ECS_CHILD_EXIT_NONZERO")

    def _read_result(self, key: str, *, sandbox_id: UUID) -> dict[str, Any]:
        response = self._s3.get_object(Bucket=self._bucket, Key=key)
        length = response.get("ContentLength")
        if not isinstance(length, int) or length <= 0 or length > _MAX_EXCHANGE_BYTES:
            raise ECSRemoteSandboxError("SANDBOX_REMOTE_RESULT_SIZE_INVALID")
        raw = response["Body"].read(_MAX_EXCHANGE_BYTES + 1)
        if len(raw) != length or len(raw) > _MAX_EXCHANGE_BYTES:
            raise ECSRemoteSandboxError("SANDBOX_REMOTE_RESULT_SIZE_INVALID")
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict) or payload.get("sandbox_id") != str(sandbox_id):
            raise ECSRemoteSandboxError("SANDBOX_REMOTE_RESULT_IDENTITY_INVALID")
        for key_name in ("stdout", "stderr"):
            if not isinstance(payload.get(key_name), str):
                raise ECSRemoteSandboxError("SANDBOX_REMOTE_RESULT_TEXT_INVALID")
        for key_name in ("stdout_truncated", "stderr_truncated"):
            if not isinstance(payload.get(key_name), bool):
                raise ECSRemoteSandboxError("SANDBOX_REMOTE_RESULT_TRUNCATION_INVALID")
        exit_code = payload.get("exit_code")
        duration_ms = payload.get("duration_ms")
        if isinstance(exit_code, bool) or not isinstance(exit_code, int):
            raise ECSRemoteSandboxError("SANDBOX_REMOTE_RESULT_EXIT_INVALID")
        if isinstance(duration_ms, bool) or not isinstance(duration_ms, int) or duration_ms < 0:
            raise ECSRemoteSandboxError("SANDBOX_REMOTE_RESULT_DURATION_INVALID")
        return payload

    def read_file(self, sandbox_id: UUID, path: str, *, max_bytes: int | None = None) -> bytes:
        del sandbox_id, path, max_bytes
        raise ECSRemoteSandboxError("SANDBOX_REMOTE_FILE_API_UNSUPPORTED")

    def write_file(self, sandbox_id: UUID, path: str, data: bytes) -> None:
        del sandbox_id, path, data
        raise ECSRemoteSandboxError("SANDBOX_REMOTE_FILE_API_UNSUPPORTED")

    def list_files(self, sandbox_id: UUID, path: str) -> tuple[FileEntry, ...]:
        del sandbox_id, path
        raise ECSRemoteSandboxError("SANDBOX_REMOTE_FILE_API_UNSUPPORTED")

    def upload_asset(self, sandbox_id: UUID, asset_ref: str) -> str:
        del sandbox_id, asset_ref
        raise ECSRemoteSandboxError("SANDBOX_REMOTE_ASSET_API_UNSUPPORTED")

    def collect_artifact(self, sandbox_id: UUID, path: str) -> CollectedArtifact:
        del sandbox_id, path
        raise ECSRemoteSandboxError("SANDBOX_REMOTE_ARTIFACT_API_UNSUPPORTED")

    def terminate(self, sandbox_id: UUID) -> None:
        with self._lock:
            self._sandboxes.pop(sandbox_id, None)

    def reap_expired(self) -> tuple[UUID, ...]:
        return ()


def _required_env(name: str, *, max_length: int = 4096) -> str:
    value = os.getenv(name, "")
    if not value or len(value) > max_length or "\x00" in value:
        raise RuntimeError(f"{name}_REQUIRED")
    return value


def _csv_env(name: str) -> tuple[str, ...]:
    values = tuple(part.strip() for part in _required_env(name).split(",") if part.strip())
    if not values or len(values) > 32:
        raise RuntimeError(f"{name}_INVALID")
    return values
