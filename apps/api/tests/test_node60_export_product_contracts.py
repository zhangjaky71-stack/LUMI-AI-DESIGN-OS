from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

from lumi_api.api.v1.export_product_routes import _capabilities
from lumi_api.api.v1.export_product_schemas import (
    CreateExportJobRequest,
    ExportCapabilitiesResponse,
    ExportJobResponse,
    ExportOutputResponse,
)
from lumi_export_engine import ArtifactVersionSnapshot, ExportFormat, ExportSourceFile

SHA = "a" * 64


class SnapshotReader:
    def __init__(self, snapshot: ArtifactVersionSnapshot) -> None:
        self.snapshot = snapshot
        self.calls: list[tuple[str, str, str]] = []

    def snapshot_exact(self, *, organization_id: str, project_id: str, artifact_version_id: str):
        self.calls.append((organization_id, project_id, artifact_version_id))
        return self.snapshot


class Authorization:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def authorize_snapshot(self, *, actor_id: str, snapshot: ArtifactVersionSnapshot) -> None:
        self.calls.append((actor_id, snapshot.artifact_version_id))


class Renderer:
    def supports(self, *, artifact_type: str, target_format: ExportFormat) -> bool:
        del artifact_type
        return target_format in {
            ExportFormat.PNG,
            ExportFormat.JPEG,
            ExportFormat.MP4,
            ExportFormat.PDF,
            ExportFormat.PPTX,
        }


def snapshot(mime: str) -> ArtifactVersionSnapshot:
    version_id = str(uuid4())
    file = ExportSourceFile(
        file_id=str(uuid4()),
        role="original",
        bucket="private",
        storage_key="internal/source/file.bin",
        mime_type=mime,
        size_bytes=4,
        checksum_sha256=SHA,
    )
    return ArtifactVersionSnapshot(
        organization_id=str(uuid4()),
        project_id=str(uuid4()),
        artifact_id=str(uuid4()),
        artifact_version_id=version_id,
        artifact_type="RASTER_IMAGE",
        version_number=7,
        status="APPROVED",
        content_hash=SHA,
        primary_file_id=file.file_id,
        files=(file,),
        rights_review_status="APPROVED",
        captured_at=datetime.now(UTC),
    )


def capability_for(mime: str) -> ExportCapabilitiesResponse:
    source = snapshot(mime)
    snapshots = SnapshotReader(source)
    auth = Authorization()
    engine = SimpleNamespace(
        snapshots=snapshots,
        authorization=auth,
        renderers=(Renderer(),),
    )
    result = _capabilities(
        engine,
        organization_id=UUID(source.organization_id),
        project_id=UUID(source.project_id),
        version_id=UUID(source.artifact_version_id),
        actor_id="user-1",
    )
    assert snapshots.calls == [
        (source.organization_id, source.project_id, source.artifact_version_id)
    ]
    assert auth.calls == [("user-1", source.artifact_version_id)]
    return result


def test_png_capability_is_exact_copy_through_only() -> None:
    value = capability_for("image/png")
    assert [item.format for item in value.formats] == [ExportFormat.ORIGINAL, ExportFormat.PNG]
    assert value.source_mime_type == "image/png"
    assert value.supports_resize is False
    assert value.supports_quality is False
    assert value.supports_alpha is False
    assert value.supports_print_options is False
    assert value.supports_ai_adapt is False


def test_unknown_mime_exposes_original_only() -> None:
    value = capability_for("image/webp")
    assert [item.format for item in value.formats] == [ExportFormat.ORIGINAL]


def test_product_request_does_not_claim_unimplemented_render_options() -> None:
    fields = set(CreateExportJobRequest.model_fields)
    assert fields == {"task_id", "items", "force_zip", "package_name"}
    for forbidden in (
        "width",
        "height",
        "scale",
        "quality",
        "alpha",
        "dpi",
        "cmyk",
        "bleed",
        "crop_marks",
        "ai_adapt",
    ):
        assert forbidden not in fields


def test_safe_job_output_does_not_expose_storage_locations() -> None:
    assert "bucket" not in ExportOutputResponse.model_fields
    assert "storage_key" not in ExportOutputResponse.model_fields
    assert "bucket" not in ExportJobResponse.model_fields
    assert "storage_key" not in ExportJobResponse.model_fields


def test_capability_schema_defaults_unsupported_features_false() -> None:
    fields = ExportCapabilitiesResponse.model_fields
    assert fields["supports_resize"].default is False
    assert fields["supports_quality"].default is False
    assert fields["supports_alpha"].default is False
    assert fields["supports_print_options"].default is False
    assert fields["supports_ai_adapt"].default is False
