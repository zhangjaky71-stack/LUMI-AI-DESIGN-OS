from __future__ import annotations

import json
import os
import re
import ssl
import threading
import time
import urllib.error
import urllib.request
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote
from uuid import UUID, uuid4

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from .models import CollectedArtifact, ExecRequest, ExecResult, FileEntry, SandboxSpec, SandboxState

_MAX_EXCHANGE_BYTES = 64 * 1024 * 1024
_IMAGE_DIGEST = re.compile(r"^[^\s@]+@sha256:[0-9a-f]{64}$")
_KUBERNETES_NAME = re.compile(r"^[a-z0-9](?:[-a-z0-9.]*[a-z0-9])?$")


class ACKRemoteSandboxError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class _SandboxRecord:
    spec: SandboxSpec
    state: SandboxState


class InClusterKubernetesClient:
    """Small in-cluster Batch API client with no host kubeconfig fallback."""

    def __init__(
        self,
        *,
        api_server: str,
        token: str,
        ca_file: str,
        timeout_seconds: float = 10.0,
    ) -> None:
        if not api_server.startswith("https://"):
            raise ValueError("KUBERNETES_API_SERVER_HTTPS_REQUIRED")
        if not token or "\x00" in token:
            raise ValueError("KUBERNETES_SERVICE_ACCOUNT_TOKEN_REQUIRED")
        self._api_server = api_server.rstrip("/")
        self._token = token
        self._context = ssl.create_default_context(cafile=ca_file)
        self._timeout = timeout_seconds

    @classmethod
    def from_service_account(cls) -> InClusterKubernetesClient:
        host = _required_env("KUBERNETES_SERVICE_HOST", max_length=255)
        port = os.getenv("KUBERNETES_SERVICE_PORT_HTTPS", "443")
        if not port.isdigit() or not 1 <= int(port) <= 65535:
            raise RuntimeError("KUBERNETES_SERVICE_PORT_INVALID")
        token_path = Path(
            os.getenv(
                "LUMI_KUBERNETES_TOKEN_FILE",
                "/var/run/secrets/kubernetes.io/serviceaccount/token",
            )
        )
        ca_path = Path(
            os.getenv(
                "LUMI_KUBERNETES_CA_FILE",
                "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt",
            )
        )
        token = token_path.read_text(encoding="utf-8").strip()
        return cls(
            api_server=f"https://{host}:{port}",
            token=token,
            ca_file=str(ca_path),
        )

    def create_job(self, namespace: str, body: dict[str, Any]) -> None:
        self._request(
            "POST",
            f"/apis/batch/v1/namespaces/{quote(namespace, safe='')}/jobs",
            body,
        )

    def read_job(self, namespace: str, name: str) -> dict[str, Any]:
        return self._request(
            "GET",
            f"/apis/batch/v1/namespaces/{quote(namespace, safe='')}/jobs/{quote(name, safe='')}",
        )

    def delete_job(self, namespace: str, name: str) -> None:
        self._request(
            "DELETE",
            f"/apis/batch/v1/namespaces/{quote(namespace, safe='')}/jobs/{quote(name, safe='')}",
            {"apiVersion": "v1", "kind": "DeleteOptions", "propagationPolicy": "Background"},
        )

    def _request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        encoded = None
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self._token}",
            "User-Agent": "LUMI-SandboxRuntime/1.0",
        }
        if body is not None:
            encoded = json.dumps(body, separators=(",", ":")).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            f"{self._api_server}{path}",
            data=encoded,
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(
                request,
                context=self._context,
                timeout=self._timeout,
            ) as response:
                raw = response.read(2 * 1024 * 1024 + 1)
        except (OSError, urllib.error.URLError) as exc:
            raise ACKRemoteSandboxError("SANDBOX_ACK_API_REQUEST_FAILED") from exc
        if len(raw) > 2 * 1024 * 1024:
            raise ACKRemoteSandboxError("SANDBOX_ACK_API_RESPONSE_TOO_LARGE")
        if not raw:
            return {}
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ACKRemoteSandboxError("SANDBOX_ACK_API_RESPONSE_INVALID") from exc
        if not isinstance(payload, dict):
            raise ACKRemoteSandboxError("SANDBOX_ACK_API_RESPONSE_INVALID")
        return payload


class ACKRemoteSandboxBackend:
    """ACK Auto Mode backend; every command runs in a short-lived Kubernetes Job."""

    def __init__(
        self,
        *,
        namespace: str,
        child_image: str,
        child_service_account: str,
        oss_secret_name: str,
        child_vswitch_ids: tuple[str, ...],
        child_security_group_id: str,
        exchange_bucket: str,
        s3_endpoint_url: str,
        s3_region: str,
        s3_signature_version: str = "s3",
        job_ttl_seconds: int = 300,
        poll_interval_seconds: float = 2.0,
        kubernetes_client: Any | None = None,
        s3_client: Any | None = None,
    ) -> None:
        for value in (namespace, child_service_account, oss_secret_name):
            if len(value) > 253 or _KUBERNETES_NAME.fullmatch(value) is None:
                raise ValueError("SANDBOX_ACK_KUBERNETES_NAME_INVALID")
        if _IMAGE_DIGEST.fullmatch(child_image) is None:
            raise ValueError("SANDBOX_ACK_CHILD_IMAGE_DIGEST_REQUIRED")
        if not child_vswitch_ids or not all(child_vswitch_ids):
            raise ValueError("SANDBOX_ACK_CHILD_VSWITCH_REQUIRED")
        if not child_security_group_id:
            raise ValueError("SANDBOX_ACK_CHILD_SECURITY_GROUP_REQUIRED")
        if not exchange_bucket or "/" in exchange_bucket:
            raise ValueError("SANDBOX_EXCHANGE_BUCKET_INVALID")
        if not s3_endpoint_url.startswith("https://"):
            raise ValueError("SANDBOX_OSS_HTTPS_ENDPOINT_REQUIRED")
        if s3_signature_version not in {"s3", "s3v4"}:
            raise ValueError("SANDBOX_S3_SIGNATURE_VERSION_INVALID")
        if not 30 <= job_ttl_seconds <= 86_400:
            raise ValueError("SANDBOX_ACK_JOB_TTL_INVALID")
        if poll_interval_seconds < 0:
            raise ValueError("SANDBOX_ACK_POLL_INTERVAL_INVALID")

        self._namespace = namespace
        self._child_image = child_image
        self._child_service_account = child_service_account
        self._oss_secret_name = oss_secret_name
        self._child_vswitch_ids = child_vswitch_ids
        self._child_security_group_id = child_security_group_id
        self._bucket = exchange_bucket
        self._endpoint = s3_endpoint_url
        self._region = s3_region
        self._signature = s3_signature_version
        self._job_ttl_seconds = job_ttl_seconds
        self._poll_interval_seconds = poll_interval_seconds
        self._kubernetes = kubernetes_client or InClusterKubernetesClient.from_service_account()
        self._s3 = s3_client or _s3_client(
            endpoint_url=s3_endpoint_url,
            region=s3_region,
            signature_version=s3_signature_version,
        )
        self._lock = threading.Lock()
        self._sandboxes: dict[UUID, _SandboxRecord] = {}

    @classmethod
    def from_env(cls) -> ACKRemoteSandboxBackend:
        return cls(
            namespace=_required_env("LUMI_SANDBOX_ACK_NAMESPACE", max_length=253),
            child_image=_required_env("LUMI_SANDBOX_CHILD_IMAGE", max_length=1024),
            child_service_account=_required_env(
                "LUMI_SANDBOX_CHILD_SERVICE_ACCOUNT", max_length=253
            ),
            oss_secret_name=_required_env("LUMI_SANDBOX_OSS_SECRET_NAME", max_length=253),
            child_vswitch_ids=_csv_env("LUMI_SANDBOX_CHILD_VSWITCH_IDS"),
            child_security_group_id=_required_env(
                "LUMI_SANDBOX_CHILD_SECURITY_GROUP_ID", max_length=255
            ),
            exchange_bucket=_required_env("LUMI_SANDBOX_EXCHANGE_BUCKET", max_length=255),
            s3_endpoint_url=_required_env("LUMI_S3_ENDPOINT_URL", max_length=2048),
            s3_region=_required_env("LUMI_S3_REGION", max_length=64),
            s3_signature_version=os.getenv("LUMI_S3_SIGNATURE_VERSION", "s3"),
            job_ttl_seconds=_int_env(
                "LUMI_SANDBOX_JOB_TTL_SECONDS", default=300, minimum=30, maximum=86_400
            ),
        )

    def create(self, spec: SandboxSpec) -> UUID:
        if spec.network_policy.value != "NONE":
            raise ACKRemoteSandboxError("SANDBOX_REMOTE_NETWORK_POLICY_UNSUPPORTED")
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
                raise ACKRemoteSandboxError("SANDBOX_NOT_READY")
            self._sandboxes[sandbox_id] = _SandboxRecord(record.spec, SandboxState.RUNNING)
        spec = record.spec
        operation_id = uuid4()
        prefix = (
            f"sandbox-exchange/v1/{spec.organization_id}/{spec.agent_run_id}/"
            f"{sandbox_id}/{operation_id}"
        )
        request_key = f"{prefix}/request.json"
        result_key = f"{prefix}/result.json"
        job_name = f"lumi-sandbox-{operation_id.hex[:24]}"
        payload = _request_payload(sandbox_id, spec, request)
        encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        if len(encoded) > 128 * 1024:
            raise ACKRemoteSandboxError("SANDBOX_REMOTE_REQUEST_TOO_LARGE")

        job_created = False
        try:
            self._s3.put_object(
                Bucket=self._bucket,
                Key=request_key,
                Body=encoded,
                ContentType="application/json",
                Metadata={"sandbox-id": str(sandbox_id), "schema-version": "1"},
            )
            job = self._job_body(
                name=job_name,
                spec=spec,
                timeout_seconds=int(payload["timeout_seconds"]),
                request_key=request_key,
                result_key=result_key,
            )
            self._kubernetes.create_job(self._namespace, job)
            job_created = True
            self._wait_job(job_name, timeout_seconds=int(payload["timeout_seconds"]))
            result = self._read_result(result_key, sandbox_id=sandbox_id)
            self._validate_exchange_outputs(result, request)
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
                log_ref=f"ack-job://{self._namespace}/{job_name}",
            )
        except (
            BotoCoreError,
            ClientError,
            ACKRemoteSandboxError,
            UnicodeDecodeError,
            json.JSONDecodeError,
        ) as exc:
            with self._lock:
                if sandbox_id in self._sandboxes:
                    self._sandboxes[sandbox_id] = _SandboxRecord(spec, SandboxState.FAILED)
            raise ACKRemoteSandboxError("SANDBOX_REMOTE_EXECUTION_FAILED") from exc
        finally:
            if job_created:
                with suppress(ACKRemoteSandboxError):
                    self._kubernetes.delete_job(self._namespace, job_name)
            for key in (request_key, result_key):
                with suppress(BotoCoreError, ClientError):
                    self._s3.delete_object(Bucket=self._bucket, Key=key)

    def _job_body(
        self,
        *,
        name: str,
        spec: SandboxSpec,
        timeout_seconds: int,
        request_key: str,
        result_key: str,
    ) -> dict[str, Any]:
        labels = {
            "app.kubernetes.io/name": "lumi-sandbox-child",
            "app.kubernetes.io/component": "sandbox",
            "lumi.dev/sandbox-role": "child",
        }
        environment: list[dict[str, Any]] = [
            {"name": "LUMI_SANDBOX_EXCHANGE_BUCKET", "value": self._bucket},
            {"name": "LUMI_SANDBOX_REQUEST_KEY", "value": request_key},
            {"name": "LUMI_SANDBOX_RESULT_KEY", "value": result_key},
            {"name": "LUMI_S3_ENDPOINT_URL", "value": self._endpoint},
            {"name": "LUMI_S3_REGION", "value": self._region},
            {"name": "LUMI_S3_SIGNATURE_VERSION", "value": self._signature},
            {"name": "LUMI_S3_FORCE_PATH_STYLE", "value": "false"},
        ]
        for env_name, secret_key, optional in (
            ("LUMI_S3_ACCESS_KEY_ID", "access-key-id", False),
            ("LUMI_S3_SECRET_ACCESS_KEY", "secret-access-key", False),
            ("LUMI_S3_SESSION_TOKEN", "session-token", True),
        ):
            environment.append(
                {
                    "name": env_name,
                    "valueFrom": {
                        "secretKeyRef": {
                            "name": self._oss_secret_name,
                            "key": secret_key,
                            "optional": optional,
                        }
                    },
                }
            )
        annotations = {
            "k8s.aliyun.com/eci-vswitch": ",".join(self._child_vswitch_ids),
            "k8s.aliyun.com/eci-security-group": self._child_security_group_id,
        }
        return {
            "apiVersion": "batch/v1",
            "kind": "Job",
            "metadata": {"name": name, "namespace": self._namespace, "labels": labels},
            "spec": {
                "backoffLimit": 0,
                "activeDeadlineSeconds": timeout_seconds + 60,
                "ttlSecondsAfterFinished": self._job_ttl_seconds,
                "template": {
                    "metadata": {"labels": labels, "annotations": annotations},
                    "spec": {
                        "serviceAccountName": self._child_service_account,
                        "automountServiceAccountToken": False,
                        "restartPolicy": "Never",
                        "enableServiceLinks": False,
                        "securityContext": {
                            "runAsNonRoot": True,
                            "runAsUser": 10001,
                            "runAsGroup": 10001,
                            "fsGroup": 10001,
                            "seccompProfile": {"type": "RuntimeDefault"},
                        },
                        "containers": [
                            {
                                "name": "sandbox-child",
                                "image": self._child_image,
                                "imagePullPolicy": "IfNotPresent",
                                "command": ["lumi-sandbox-child"],
                                "env": environment,
                                "resources": {
                                    "requests": {
                                        "cpu": _cpu_quantity(spec.cpu_limit),
                                        "memory": f"{spec.memory_limit_mb}Mi",
                                        "ephemeral-storage": f"{spec.disk_limit_mb}Mi",
                                    },
                                    "limits": {
                                        "cpu": _cpu_quantity(spec.cpu_limit),
                                        "memory": f"{spec.memory_limit_mb}Mi",
                                        "ephemeral-storage": f"{spec.disk_limit_mb}Mi",
                                    },
                                },
                                "securityContext": {
                                    "allowPrivilegeEscalation": False,
                                    "readOnlyRootFilesystem": True,
                                    "capabilities": {"drop": ["ALL"]},
                                },
                                "volumeMounts": [{"name": "scratch", "mountPath": "/tmp"}],
                            }
                        ],
                        "volumes": [
                            {
                                "name": "scratch",
                                "emptyDir": {"sizeLimit": f"{spec.disk_limit_mb}Mi"},
                            }
                        ],
                    },
                },
            },
        }

    def _wait_job(self, name: str, *, timeout_seconds: int) -> None:
        deadline = time.monotonic() + timeout_seconds + 120
        while time.monotonic() < deadline:
            job = self._kubernetes.read_job(self._namespace, name)
            status = job.get("status", {})
            if not isinstance(status, dict):
                raise ACKRemoteSandboxError("SANDBOX_ACK_JOB_STATUS_INVALID")
            if status.get("succeeded") == 1:
                return
            failed = status.get("failed", 0)
            if isinstance(failed, int) and not isinstance(failed, bool) and failed > 0:
                raise ACKRemoteSandboxError("SANDBOX_ACK_CHILD_EXIT_NONZERO")
            time.sleep(self._poll_interval_seconds)
        raise ACKRemoteSandboxError("SANDBOX_ACK_JOB_TIMEOUT")

    def _read_result(self, key: str, *, sandbox_id: UUID) -> dict[str, Any]:
        response = self._s3.get_object(Bucket=self._bucket, Key=key)
        length = response.get("ContentLength")
        if not isinstance(length, int) or length <= 0 or length > _MAX_EXCHANGE_BYTES:
            raise ACKRemoteSandboxError("SANDBOX_REMOTE_RESULT_SIZE_INVALID")
        raw = response["Body"].read(_MAX_EXCHANGE_BYTES + 1)
        if len(raw) != length or len(raw) > _MAX_EXCHANGE_BYTES:
            raise ACKRemoteSandboxError("SANDBOX_REMOTE_RESULT_SIZE_INVALID")
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict) or payload.get("sandbox_id") != str(sandbox_id):
            raise ACKRemoteSandboxError("SANDBOX_REMOTE_RESULT_IDENTITY_INVALID")
        for key_name in ("stdout", "stderr"):
            if not isinstance(payload.get(key_name), str):
                raise ACKRemoteSandboxError("SANDBOX_REMOTE_RESULT_TEXT_INVALID")
        for key_name in ("stdout_truncated", "stderr_truncated"):
            if not isinstance(payload.get(key_name), bool):
                raise ACKRemoteSandboxError("SANDBOX_REMOTE_RESULT_TRUNCATION_INVALID")
        exit_code = payload.get("exit_code")
        duration_ms = payload.get("duration_ms")
        if isinstance(exit_code, bool) or not isinstance(exit_code, int):
            raise ACKRemoteSandboxError("SANDBOX_REMOTE_RESULT_EXIT_INVALID")
        if isinstance(duration_ms, bool) or not isinstance(duration_ms, int) or duration_ms < 0:
            raise ACKRemoteSandboxError("SANDBOX_REMOTE_RESULT_DURATION_INVALID")
        outputs = payload.get("exchange_outputs", [])
        if not isinstance(outputs, list) or len(outputs) > 16:
            raise ACKRemoteSandboxError("SANDBOX_REMOTE_RESULT_OUTPUTS_INVALID")
        return payload

    def _validate_exchange_outputs(self, result: dict[str, Any], request: ExecRequest) -> None:
        raw_outputs = result.get("exchange_outputs", [])
        if result["exit_code"] != 0:
            if raw_outputs:
                raise ACKRemoteSandboxError("SANDBOX_REMOTE_FAILED_EXEC_HAS_OUTPUTS")
            return
        if len(raw_outputs) != len(request.exchange_outputs):
            raise ACKRemoteSandboxError("SANDBOX_REMOTE_RESULT_OUTPUT_COUNT_MISMATCH")
        expected = {(item.exchange_key, item.path): item for item in request.exchange_outputs}
        seen: set[tuple[str, str]] = set()
        for raw in raw_outputs:
            if not isinstance(raw, dict):
                raise ACKRemoteSandboxError("SANDBOX_REMOTE_RESULT_OUTPUT_INVALID")
            key = raw.get("exchange_key")
            path = raw.get("path")
            if not isinstance(key, str) or not isinstance(path, str):
                raise ACKRemoteSandboxError("SANDBOX_REMOTE_RESULT_OUTPUT_IDENTITY_INVALID")
            identity = (key, path)
            item = expected.get(identity)
            if item is None or identity in seen:
                raise ACKRemoteSandboxError("SANDBOX_REMOTE_RESULT_OUTPUT_IDENTITY_INVALID")
            seen.add(identity)
            size = raw.get("size_bytes")
            sha256 = raw.get("sha256")
            if (
                isinstance(size, bool)
                or not isinstance(size, int)
                or size <= 0
                or size > item.max_bytes
            ):
                raise ACKRemoteSandboxError("SANDBOX_REMOTE_RESULT_OUTPUT_SIZE_INVALID")
            if (
                not isinstance(sha256, str)
                or len(sha256) != 64
                or any(character not in "0123456789abcdef" for character in sha256)
            ):
                raise ACKRemoteSandboxError("SANDBOX_REMOTE_RESULT_OUTPUT_SHA256_INVALID")
            if raw.get("content_type") != item.content_type:
                raise ACKRemoteSandboxError("SANDBOX_REMOTE_RESULT_OUTPUT_CONTENT_TYPE_MISMATCH")

    def read_file(self, sandbox_id: UUID, path: str, *, max_bytes: int | None = None) -> bytes:
        del sandbox_id, path, max_bytes
        raise ACKRemoteSandboxError("SANDBOX_REMOTE_FILE_API_UNSUPPORTED")

    def write_file(self, sandbox_id: UUID, path: str, data: bytes) -> None:
        del sandbox_id, path, data
        raise ACKRemoteSandboxError("SANDBOX_REMOTE_FILE_API_UNSUPPORTED")

    def list_files(self, sandbox_id: UUID, path: str) -> tuple[FileEntry, ...]:
        del sandbox_id, path
        raise ACKRemoteSandboxError("SANDBOX_REMOTE_FILE_API_UNSUPPORTED")

    def upload_asset(self, sandbox_id: UUID, asset_ref: str) -> str:
        del sandbox_id, asset_ref
        raise ACKRemoteSandboxError("SANDBOX_REMOTE_ASSET_API_UNSUPPORTED")

    def collect_artifact(self, sandbox_id: UUID, path: str) -> CollectedArtifact:
        del sandbox_id, path
        raise ACKRemoteSandboxError("SANDBOX_REMOTE_ARTIFACT_API_UNSUPPORTED")

    def terminate(self, sandbox_id: UUID) -> None:
        with self._lock:
            self._sandboxes.pop(sandbox_id, None)

    def reap_expired(self) -> tuple[UUID, ...]:
        return ()


def _request_payload(sandbox_id: UUID, spec: SandboxSpec, request: ExecRequest) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "sandbox_id": str(sandbox_id),
        "organization_id": str(spec.organization_id),
        "agent_run_id": str(spec.agent_run_id),
        "command": list(request.command),
        "cwd": request.cwd,
        "timeout_seconds": request.timeout_seconds or spec.timeout_seconds,
        "max_output_bytes": spec.max_output_bytes,
        "exchange_inputs": [
            {
                "exchange_key": item.exchange_key,
                "path": item.path,
                "max_bytes": item.max_bytes,
                "expected_sha256": item.expected_sha256,
            }
            for item in request.exchange_inputs
        ],
        "exchange_outputs": [
            {
                "exchange_key": item.exchange_key,
                "path": item.path,
                "max_bytes": item.max_bytes,
                "content_type": item.content_type,
            }
            for item in request.exchange_outputs
        ],
    }


def _s3_client(*, endpoint_url: str, region: str, signature_version: str) -> Any:
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        region_name=region,
        aws_access_key_id=os.getenv("LUMI_S3_ACCESS_KEY_ID") or None,
        aws_secret_access_key=os.getenv("LUMI_S3_SECRET_ACCESS_KEY") or None,
        aws_session_token=os.getenv("LUMI_S3_SESSION_TOKEN") or None,
        config=Config(
            signature_version=signature_version,
            retries={"mode": "standard", "max_attempts": 4},
            s3={"addressing_style": "virtual"},
        ),
    )


def _cpu_quantity(value: float) -> str:
    millicpu = int(round(value * 1000))
    return str(millicpu // 1000) if millicpu % 1000 == 0 else f"{millicpu}m"


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


def _int_env(name: str, *, default: int, minimum: int, maximum: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name}_INVALID") from exc
    if not minimum <= value <= maximum:
        raise RuntimeError(f"{name}_OUT_OF_RANGE")
    return value
