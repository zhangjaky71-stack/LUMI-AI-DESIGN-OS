from __future__ import annotations

import io
import json
import os
import unittest
from unittest.mock import patch
from uuid import uuid4

from lumi_sandbox_runtime.ack_backend import ACKRemoteSandboxBackend
from lumi_sandbox_runtime.hosted_service import _remote_backend
from lumi_sandbox_runtime.models import ExecRequest, SandboxSpec, SandboxState


class _FakeS3:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self.deleted: list[tuple[str, str]] = []

    def put_object(self, **kwargs: object) -> dict[str, object]:
        body = kwargs["Body"]
        assert isinstance(body, bytes)
        self.objects[(str(kwargs["Bucket"]), str(kwargs["Key"]))] = body
        return {}

    def get_object(self, **kwargs: object) -> dict[str, object]:
        body = self.objects[(str(kwargs["Bucket"]), str(kwargs["Key"]))]
        return {"ContentLength": len(body), "Body": io.BytesIO(body)}

    def delete_object(self, **kwargs: object) -> dict[str, object]:
        identity = (str(kwargs["Bucket"]), str(kwargs["Key"]))
        self.deleted.append(identity)
        self.objects.pop(identity, None)
        return {}


class _FakeKubernetes:
    def __init__(self, s3: _FakeS3, bucket: str) -> None:
        self.s3 = s3
        self.bucket = bucket
        self.jobs: list[dict[str, object]] = []
        self.deleted: list[tuple[str, str]] = []

    def create_job(self, namespace: str, body: dict[str, object]) -> None:
        self.jobs.append(body)
        template = body["spec"]  # type: ignore[index]
        pod = template["template"]["spec"]  # type: ignore[index]
        environment = pod["containers"][0]["env"]  # type: ignore[index]
        values = {row["name"]: row["value"] for row in environment if "value" in row}
        request_key = values["LUMI_SANDBOX_REQUEST_KEY"]
        result_key = values["LUMI_SANDBOX_RESULT_KEY"]
        request = json.loads(self.s3.objects[(self.bucket, request_key)].decode("utf-8"))
        result = {
            "schema_version": 1,
            "sandbox_id": request["sandbox_id"],
            "organization_id": request["organization_id"],
            "agent_run_id": request["agent_run_id"],
            "exit_code": 0,
            "stdout": "ack-ok",
            "stderr": "",
            "stdout_truncated": False,
            "stderr_truncated": False,
            "duration_ms": 7,
            "exchange_outputs": [],
        }
        self.s3.objects[(self.bucket, result_key)] = json.dumps(result).encode("utf-8")
        assert namespace == "lumi-staging"

    def read_job(self, namespace: str, name: str) -> dict[str, object]:
        assert namespace == "lumi-staging"
        assert name.startswith("lumi-sandbox-")
        return {"status": {"succeeded": 1}}

    def delete_job(self, namespace: str, name: str) -> None:
        self.deleted.append((namespace, name))


class ACKRemoteSandboxBackendTests(unittest.TestCase):
    def _backend(self) -> tuple[ACKRemoteSandboxBackend, _FakeS3, _FakeKubernetes]:
        s3 = _FakeS3()
        kubernetes = _FakeKubernetes(s3, "lumi-staging-sandbox")
        backend = ACKRemoteSandboxBackend(
            namespace="lumi-staging",
            child_image=(
                "registry.cn-hangzhou.aliyuncs.com/lumi/sandbox-runtime@sha256:" + "a" * 64
            ),
            child_service_account="lumi-sandbox-child",
            oss_secret_name="lumi-oss-sandbox",
            child_vswitch_ids=("vsw-a", "vsw-b", "vsw-c"),
            child_security_group_id="sg-sandbox",
            exchange_bucket="lumi-staging-sandbox",
            s3_endpoint_url="https://s3.oss-cn-hangzhou-internal.aliyuncs.com",
            s3_region="cn-hangzhou",
            kubernetes_client=kubernetes,
            s3_client=s3,
            poll_interval_seconds=0,
        )
        return backend, s3, kubernetes

    def test_exec_creates_hardened_digest_pinned_job_and_cleans_exchange(self) -> None:
        backend, s3, kubernetes = self._backend()
        sandbox_id = backend.create(SandboxSpec(uuid4(), uuid4()))
        result = backend.exec(sandbox_id, ExecRequest(("python", "-V")))

        self.assertEqual(result.stdout, "ack-ok")
        self.assertEqual(backend.state(sandbox_id), SandboxState.IDLE)
        self.assertEqual(len(kubernetes.jobs), 1)
        self.assertEqual(len(kubernetes.deleted), 1)
        self.assertEqual(len(s3.deleted), 2)
        self.assertEqual(s3.objects, {})

        job = kubernetes.jobs[0]
        spec = job["spec"]  # type: ignore[index]
        self.assertEqual(spec["backoffLimit"], 0)  # type: ignore[index]
        pod = spec["template"]["spec"]  # type: ignore[index]
        self.assertFalse(pod["automountServiceAccountToken"])
        self.assertEqual(pod["serviceAccountName"], "lumi-sandbox-child")
        container = pod["containers"][0]
        self.assertIn("@sha256:", container["image"])
        self.assertTrue(container["securityContext"]["readOnlyRootFilesystem"])
        self.assertEqual(container["securityContext"]["capabilities"]["drop"], ["ALL"])
        annotations = spec["template"]["metadata"]["annotations"]  # type: ignore[index]
        self.assertEqual(annotations["k8s.aliyun.com/eci-security-group"], "sg-sandbox")

    def test_child_image_must_be_immutable(self) -> None:
        with self.assertRaisesRegex(ValueError, "CHILD_IMAGE_DIGEST_REQUIRED"):
            ACKRemoteSandboxBackend(
                namespace="lumi-staging",
                child_image="registry.example/lumi/sandbox-runtime:latest",
                child_service_account="lumi-sandbox-child",
                oss_secret_name="lumi-oss-sandbox",
                child_vswitch_ids=("vsw-a",),
                child_security_group_id="sg-sandbox",
                exchange_bucket="lumi-staging-sandbox",
                s3_endpoint_url="https://s3.oss-cn-hangzhou.aliyuncs.com",
                s3_region="cn-hangzhou",
                kubernetes_client=object(),
                s3_client=object(),
            )

    def test_hosted_service_selects_ack_only_when_requested(self) -> None:
        sentinel = object()
        with (
            patch.dict(os.environ, {"LUMI_SANDBOX_REMOTE_BACKEND": "ack"}, clear=False),
            patch(
                "lumi_sandbox_runtime.hosted_service.ACKRemoteSandboxBackend.from_env",
                return_value=sentinel,
            ),
        ):
            self.assertIs(_remote_backend(), sentinel)


if __name__ == "__main__":
    unittest.main()
