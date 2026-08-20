from __future__ import annotations

import hashlib
import subprocess
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from lumi_sandbox_runtime import ExchangeInputFile, ExchangeOutputFile, ExecRequest
from lumi_sandbox_runtime.child_cli import ChildExecutionError, _execute


class _FakeS3:
    def __init__(self, objects: dict[str, bytes]) -> None:
        self.objects = dict(objects)
        self.upload_metadata: dict[str, dict[str, object]] = {}

    def head_object(self, *, Bucket: str, Key: str) -> dict[str, object]:
        self._bucket(Bucket)
        if Key not in self.objects:
            raise AssertionError(f"missing fake object: {Key}")
        return {"ContentLength": len(self.objects[Key])}

    def download_file(self, bucket: str, key: str, filename: str) -> None:
        self._bucket(bucket)
        Path(filename).write_bytes(self.objects[key])

    def upload_file(
        self,
        filename: str,
        bucket: str,
        key: str,
        ExtraArgs: dict[str, object] | None = None,
    ) -> None:
        self._bucket(bucket)
        self.objects[key] = Path(filename).read_bytes()
        self.upload_metadata[key] = dict(ExtraArgs or {})

    @staticmethod
    def _bucket(value: str) -> None:
        if value != "sandbox-exchange-test":
            raise AssertionError(f"unexpected bucket: {value}")


class ExchangeContractTests(unittest.TestCase):
    def test_contract_rejects_escape_duplicate_and_noncanonical_keys(self) -> None:
        with self.assertRaisesRegex(ValueError, "EXCHANGE_KEY_INVALID"):
            ExchangeInputFile("business-assets/input.mp4", "input/a.mp4", 1024)
        with self.assertRaisesRegex(ValueError, "EXCHANGE_PATH_INVALID"):
            ExchangeOutputFile(
                "sandbox-exchange/v1/org/run/out.mp4",
                "output/../escape.mp4",
                1024,
            )
        item = ExchangeInputFile(
            "sandbox-exchange/v1/org/run/in.mp4",
            "input/a.mp4",
            1024,
        )
        with self.assertRaisesRegex(ValueError, "EXCHANGE_PATH_DUPLICATE"):
            ExecRequest(
                ("tool",),
                exchange_inputs=(item,),
                exchange_outputs=(
                    ExchangeOutputFile(
                        "sandbox-exchange/v1/org/run/out.mp4",
                        "input/a.mp4",
                        1024,
                    ),
                ),
            )

    def test_child_streams_exchange_input_and_output_with_sha256(self) -> None:
        source = b"fake-video-source" * 1024
        source_sha = hashlib.sha256(source).hexdigest()
        input_key = "sandbox-exchange/v1/org/run/input/clip.mp4"
        output_key = "sandbox-exchange/v1/org/run/output/render.mp4"
        s3 = _FakeS3({input_key: source})
        payload = {
            "sandbox_id": str(uuid4()),
            "organization_id": str(uuid4()),
            "agent_run_id": str(uuid4()),
            "command": [
                "ffmpeg",
                "-i",
                "/sandbox/input/clip.mp4",
                "/sandbox/output/render.mp4",
            ],
            "cwd": "work",
            "timeout_seconds": 30,
            "max_output_bytes": 1024 * 1024,
            "exchange_inputs": [
                {
                    "exchange_key": input_key,
                    "path": "input/clip.mp4",
                    "max_bytes": len(source),
                    "expected_sha256": source_sha,
                }
            ],
            "exchange_outputs": [
                {
                    "exchange_key": output_key,
                    "path": "output/render.mp4",
                    "max_bytes": len(source) + 64,
                    "content_type": "video/mp4",
                }
            ],
        }

        def fake_run(command: list[str], **kwargs: object) -> SimpleNamespace:
            self.assertEqual(command[0], "ffmpeg")
            self.assertNotIn("/sandbox/", " ".join(command))
            input_path = Path(command[2])
            output_path = Path(command[3])
            self.assertTrue(input_path.is_file())
            self.assertEqual(input_path.read_bytes(), source)
            self.assertEqual(input_path.stat().st_mode & 0o777, 0o400)
            self.assertEqual(Path(str(kwargs["cwd"])).name, "work")
            output_path.write_bytes(source + b"-rendered")
            return SimpleNamespace(returncode=0, stdout=b"ok", stderr=b"")

        with patch.object(subprocess, "run", side_effect=fake_run):
            result = _execute(payload, s3=s3, bucket="sandbox-exchange-test")

        rendered = source + b"-rendered"
        self.assertEqual(result["exit_code"], 0)
        self.assertEqual(s3.objects[output_key], rendered)
        self.assertEqual(len(result["exchange_outputs"]), 1)
        output = result["exchange_outputs"][0]
        self.assertEqual(output["exchange_key"], output_key)
        self.assertEqual(output["size_bytes"], len(rendered))
        self.assertEqual(output["sha256"], hashlib.sha256(rendered).hexdigest())
        self.assertEqual(output["content_type"], "video/mp4")
        metadata = s3.upload_metadata[output_key]
        self.assertEqual(metadata["ContentType"], "video/mp4")
        self.assertEqual(
            metadata["Metadata"],
            {"sha256": hashlib.sha256(rendered).hexdigest(), "schema-version": "1"},
        )

    def test_child_rejects_input_checksum_mismatch_before_process_execution(self) -> None:
        source = b"corrupted-video"
        input_key = "sandbox-exchange/v1/org/run/input/clip.mp4"
        s3 = _FakeS3({input_key: source})
        payload = {
            "sandbox_id": str(uuid4()),
            "organization_id": str(uuid4()),
            "agent_run_id": str(uuid4()),
            "command": ["ffmpeg", "-i", "/sandbox/input/clip.mp4", "null.mp4"],
            "timeout_seconds": 30,
            "max_output_bytes": 4096,
            "exchange_inputs": [
                {
                    "exchange_key": input_key,
                    "path": "input/clip.mp4",
                    "max_bytes": len(source),
                    "expected_sha256": "0" * 64,
                }
            ],
            "exchange_outputs": [],
        }
        with patch.object(subprocess, "run") as run:
            with self.assertRaisesRegex(
                ChildExecutionError,
                "EXCHANGE_INPUT_CHECKSUM_MISMATCH",
            ):
                _execute(payload, s3=s3, bucket="sandbox-exchange-test")
            run.assert_not_called()

    def test_failed_process_never_uploads_declared_output(self) -> None:
        output_key = "sandbox-exchange/v1/org/run/output/render.mp4"
        s3 = _FakeS3({})
        payload = {
            "sandbox_id": str(uuid4()),
            "organization_id": str(uuid4()),
            "agent_run_id": str(uuid4()),
            "command": ["ffmpeg", "-version"],
            "timeout_seconds": 30,
            "max_output_bytes": 4096,
            "exchange_inputs": [],
            "exchange_outputs": [
                {
                    "exchange_key": output_key,
                    "path": "output/render.mp4",
                    "max_bytes": 1024,
                    "content_type": "video/mp4",
                }
            ],
        }
        with patch.object(
            subprocess,
            "run",
            return_value=SimpleNamespace(returncode=2, stdout=b"", stderr=b"failed"),
        ):
            result = _execute(payload, s3=s3, bucket="sandbox-exchange-test")
        self.assertEqual(result["exit_code"], 2)
        self.assertEqual(result["exchange_outputs"], [])
        self.assertNotIn(output_key, s3.objects)


if __name__ == "__main__":
    unittest.main()
