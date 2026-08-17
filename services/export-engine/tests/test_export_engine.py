from __future__ import annotations

import asyncio
import hashlib
import io
import json
import zipfile
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from lumi_export_engine.model import (
    ArtifactVersionSnapshot,
    DownloadGrant,
    ExportFormat,
    ExportJobStatus,
    ExportRequestItem,
    ExportSourceFile,
    ExportTaskSpec,
)
from lumi_export_engine.pipeline import ExportEngine, ExportOperationConflict
from lumi_export_engine.repository import InMemoryExportRepository


class Snapshots:
    def __init__(self, values):
        self.values = values
        self.calls = []

    def snapshot_exact(self, **kwargs):
        self.calls.append(kwargs["artifact_version_id"])
        return self.values[kwargs["artifact_version_id"]]


class Auth:
    def __init__(self, deny=False):
        self.deny = deny
        self.snapshot_checks = 0
        self.download_checks = 0

    def authorize_snapshot(self, **kwargs):
        self.snapshot_checks += 1
        if self.deny:
            raise PermissionError("denied")

    def authorize_download(self, **kwargs):
        self.download_checks += 1
        if self.deny:
            raise PermissionError("denied")


class Reader:
    def __init__(self, payloads):
        self.payloads = payloads

    async def read_exact(self, *, source):
        return self.payloads[source.storage_key]


class Store:
    def __init__(self):
        self.payloads = {}

    async def put(self, **kwargs):
        key = f"exports/{len(self.payloads)}-{kwargs['filename']}"
        self.payloads[key] = kwargs["payload"]
        assert hashlib.sha256(kwargs["payload"]).hexdigest() == kwargs["checksum_sha256"]
        return "export-bucket", key


class Queue:
    def __init__(self):
        self.enqueued = 0
        self.cancelled = []

    def enqueue(self, *, job):
        self.enqueued += 1
        return str(uuid4())

    def cancel(self, *, runtime_job_id):
        self.cancelled.append(runtime_job_id)
        return True


class Grants:
    async def issue(self, *, job, actor_id, package, ttl_seconds):
        return DownloadGrant(
            grant_id=str(uuid4()),
            package_id=package.package_id,
            actor_id=actor_id,
            expires_at=datetime.now(UTC) + timedelta(seconds=ttl_seconds),
            url="https://signed.invalid/transient-token",
        )


def snapshot(version_id: str, artifact_id: str, payload: bytes, name: str):
    checksum = hashlib.sha256(payload).hexdigest()
    return ArtifactVersionSnapshot(
        organization_id="11111111-1111-4111-8111-111111111111",
        project_id="22222222-2222-4222-8222-222222222222",
        artifact_id=artifact_id,
        artifact_version_id=version_id,
        artifact_type="IMAGE",
        version_number=3,
        status="APPROVED",
        content_hash=checksum,
        primary_file_id=f"file-{name}",
        files=(
            ExportSourceFile(
                file_id=f"file-{name}",
                role="original",
                bucket="artifact-bucket",
                storage_key=f"source/{name}.png",
                mime_type="image/png",
                size_bytes=len(payload),
                checksum_sha256=checksum,
            ),
        ),
        rights_review_status="UNREVIEWED",
        captured_at=datetime(2026, 8, 17, 12, 0, tzinfo=UTC),
    )


def build_engine(*, deny=False):
    payload_a = b"png-a"
    payload_b = b"png-b"
    version_a = "33333333-3333-4333-8333-333333333333"
    version_b = "44444444-4444-4444-8444-444444444444"
    snapshots = Snapshots(
        {
            version_a: snapshot(
                version_a,
                "55555555-5555-4555-8555-555555555555",
                payload_a,
                "a",
            ),
            version_b: snapshot(
                version_b,
                "66666666-6666-4666-8666-666666666666",
                payload_b,
                "b",
            ),
        }
    )
    auth = Auth(deny=deny)
    reader = Reader({"source/a.png": payload_a, "source/b.png": payload_b})
    store = Store()
    queue = Queue()
    repository = InMemoryExportRepository()
    engine = ExportEngine(
        snapshots=snapshots,
        authorization=auth,
        repository=repository,
        queue=queue,
        reader=reader,
        renderers=(),
        store=store,
        grants=Grants(),
    )
    return engine, repository, snapshots, auth, store, queue, version_a, version_b


def spec(version_ids, *, operation="77777777-7777-4777-8777-777777777777", force_zip=False):
    return ExportTaskSpec(
        organization_id="11111111-1111-4111-8111-111111111111",
        project_id="22222222-2222-4222-8222-222222222222",
        task_id="88888888-8888-4888-8888-888888888888",
        operation_id=operation,
        requested_by="user-1",
        items=tuple(
            ExportRequestItem(
                artifact_version_id=value,
                target_format=ExportFormat.ORIGINAL,
                output_name=f"file-{index}.png",
            )
            for index, value in enumerate(version_ids)
        ),
        force_zip=force_zip,
        package_name="campaign-export",
    )


def test_exact_version_single_file_manifest_and_download_reauth():
    async def scenario():
        engine, repository, snapshots, auth, store, _, version_a, _ = build_engine()
        queued = engine.create(spec((version_a,)))
        assert queued.status is ExportJobStatus.QUEUED
        assert snapshots.calls == [version_a]
        ready = await engine.execute(queued.job_id)
        assert ready.status is ExportJobStatus.READY
        assert ready.package is not None
        assert ready.package.is_archive is False
        assert ready.package.manifest.entries[0].artifact_version_id == version_a
        assert ready.package.checksum_sha256 == ready.outputs[0].checksum_sha256
        grant = await engine.issue_download(ready.job_id, actor_id="user-1")
        assert grant.url.startswith("https://signed.invalid/")
        assert auth.download_checks == 1
        assert "signed.invalid" not in repr(repository._grants)
        assert store.payloads[ready.package.storage_key] == b"png-a"

    asyncio.run(scenario())


def test_batch_export_builds_zip_with_manifest_and_checksums():
    async def scenario():
        engine, _, snapshots, _, store, _, version_a, version_b = build_engine()
        queued = engine.create(spec((version_a, version_b)))
        ready = await engine.execute(queued.job_id)
        assert snapshots.calls == [version_a, version_b]
        assert ready.package is not None and ready.package.is_archive is True
        archive_bytes = store.payloads[ready.package.storage_key]
        assert hashlib.sha256(archive_bytes).hexdigest() == ready.package.checksum_sha256
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
            assert set(archive.namelist()) == {"file-0.png", "file-1.png", "manifest.json"}
            manifest = json.loads(archive.read("manifest.json"))
        assert [item["artifact_version_id"] for item in manifest["entries"]] == [
            version_a,
            version_b,
        ]

    asyncio.run(scenario())


def test_permission_denied_prevents_queue_side_effect():
    engine, _, _, _, _, queue, version_a, _ = build_engine(deny=True)
    with pytest.raises(PermissionError):
        engine.create(spec((version_a,)))
    assert queue.enqueued == 0


def test_operation_id_reuse_with_changed_exact_version_conflicts():
    engine, _, _, _, _, _, version_a, version_b = build_engine()
    engine.create(spec((version_a,), operation="99999999-9999-4999-8999-999999999999"))
    with pytest.raises(ExportOperationConflict):
        engine.create(spec((version_b,), operation="99999999-9999-4999-8999-999999999999"))


def test_filename_traversal_rejected_before_any_work():
    with pytest.raises(ValueError, match="FILENAME"):
        ExportRequestItem(
            artifact_version_id="33333333-3333-4333-8333-333333333333",
            target_format=ExportFormat.ORIGINAL,
            output_name="../secret.png",
        )
