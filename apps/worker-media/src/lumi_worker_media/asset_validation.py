from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import asyncpg
from lumi_asset_storage import (
    ObjectStore,
    asset_object_key,
    require_declared_mime_matches_sniffed,
    sha256_hex_to_base64,
    sha256_path,
    sniff_media_type,
)
from lumi_domain import new_uuid7

from .asset_config import AssetWorkerSettings
from .media_tools import MediaInspection, PreviewOutput, inspect_media
from .scanner import CommandFileScanner


@dataclass(frozen=True, slots=True)
class ValidationSnapshot:
    validation_run_id: UUID
    organization_id: UUID
    project_id: UUID
    asset_id: UUID
    asset_file_id: UUID
    upload_session_id: UUID
    bucket: str
    object_key: str
    declared_mime_type: str
    declared_size: int
    expected_checksum_sha256: str
    original_name: str | None


async def validate_asset_run(
    validation_run_id: UUID,
    *,
    settings: AssetWorkerSettings,
    object_store: ObjectStore,
) -> str:
    connection = await asyncpg.connect(settings.asyncpg_dsn())
    try:
        snapshot = await _claim(connection, validation_run_id)
        if snapshot is None:
            return "SKIPPED_NOT_CLAIMABLE"
    finally:
        await connection.close()

    full_checksum: str | None = None
    scanner_status: str | None = None
    try:
        with tempfile.TemporaryDirectory(prefix="lumi-asset-") as workspace:
            source_path = str(Path(workspace) / "source.bin")
            await object_store.download_to_path(
                bucket=snapshot.bucket,
                object_key=snapshot.object_key,
                path=source_path,
            )
            actual_size = os.path.getsize(source_path)
            if actual_size != snapshot.declared_size:
                raise ValidationRejected("UPLOAD_SIZE_MISMATCH")
            full_checksum = sha256_path(source_path)
            if full_checksum != snapshot.expected_checksum_sha256:
                raise ValidationRejected("UPLOAD_CHECKSUM_MISMATCH")

            with Path(source_path).open("rb") as handle:
                sniffed = sniff_media_type(handle.read(16384))
            try:
                require_declared_mime_matches_sniffed(
                    snapshot.declared_mime_type,
                    sniffed.mime_type,
                )
            except ValueError as exc:
                raise ValidationRejected(str(exc)) from exc

            scanner = CommandFileScanner(settings.asset_scan_command)
            scanner_status = await scanner.scan_path(source_path)
            if scanner_status == "INFECTED":
                raise ValidationRejected("MALWARE_DETECTED")
            if scanner_status in {"SCAN_UNAVAILABLE", "ERROR"} and not settings.asset_allow_scan_unavailable:
                raise ValidationRejected("MALWARE_SCAN_UNAVAILABLE")

            inspection = await inspect_media(
                source_path,
                workspace=workspace,
                max_image_pixels=settings.asset_max_image_pixels,
                thumbnail_max_px=settings.asset_thumbnail_max_px,
                medium_max_px=settings.asset_medium_max_px,
                ffprobe_command=settings.asset_ffprobe_command,
                ffmpeg_command=settings.asset_ffmpeg_command,
            )
            if inspection.sniffed_mime_type != sniffed.mime_type:
                raise ValidationRejected("MIME_INSPECTION_INCONSISTENT")

            derived = await _upload_derived_files(
                object_store=object_store,
                snapshot=snapshot,
                inspection=inspection,
            )
            await _finalize_success(
                settings=settings,
                snapshot=snapshot,
                inspection=inspection,
                full_checksum=full_checksum,
                scanner_status=scanner_status,
                derived=derived,
            )
            return "READY"
    except ValidationRejected as exc:
        await _finalize_failure(
            settings=settings,
            snapshot=snapshot,
            status="rejected",
            scanner_status=scanner_status,
            full_checksum=full_checksum,
            failure_code=exc.code,
        )
        return f"REJECTED:{exc.code}"
    except Exception:
        await _finalize_failure(
            settings=settings,
            snapshot=snapshot,
            status="error",
            scanner_status=scanner_status or "ERROR",
            full_checksum=full_checksum,
            failure_code="VALIDATION_ERROR",
        )
        raise


class ValidationRejected(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class DerivedFile:
    id: UUID
    variant: str
    preview_kind: str | None
    bucket: str
    object_key: str
    checksum_sha256: str
    mime_type: str
    byte_size: int
    width: int | None
    height: int | None


async def _claim(connection: asyncpg.Connection, validation_run_id: UUID) -> ValidationSnapshot | None:
    async with connection.transaction():
        claimed = await connection.fetchrow(
            """
            UPDATE asset_validation_runs
            SET status = 'running',
                started_at = now(),
                completed_at = NULL,
                failure_code = NULL,
                updated_at = now(),
                version = version + 1
            WHERE id = $1
              AND (
                    status = 'pending'
                    OR (status = 'running' AND started_at < now() - interval '30 minutes')
                  )
            RETURNING organization_id, project_id, asset_id, asset_file_id
            """,
            validation_run_id,
        )
        if claimed is None:
            return None
        upload = await connection.fetchrow(
            """
            SELECT u.id,
                   u.bucket,
                   u.object_key,
                   u.declared_mime_type,
                   u.declared_size,
                   u.expected_checksum_sha256,
                   a.original_name
            FROM asset_upload_sessions AS u
            JOIN assets AS a
              ON a.id = u.asset_id
             AND a.organization_id = u.organization_id
            WHERE u.organization_id = $1
              AND u.project_id = $2
              AND u.asset_id = $3
              AND u.file_id = $4
              AND u.status = 'completed'
              AND a.status = 'scanning'
              AND a.deleted_at IS NULL
            ORDER BY u.created_at DESC
            LIMIT 1
            """,
            claimed["organization_id"],
            claimed["project_id"],
            claimed["asset_id"],
            claimed["asset_file_id"],
        )
        if upload is None:
            await connection.execute(
                """
                UPDATE asset_validation_runs
                SET status = 'error', failure_code = 'UPLOAD_SNAPSHOT_MISSING',
                    completed_at = now(), updated_at = now(), version = version + 1
                WHERE id = $1
                """,
                validation_run_id,
            )
            return None
        return ValidationSnapshot(
            validation_run_id=validation_run_id,
            organization_id=claimed["organization_id"],
            project_id=claimed["project_id"],
            asset_id=claimed["asset_id"],
            asset_file_id=claimed["asset_file_id"],
            upload_session_id=upload["id"],
            bucket=upload["bucket"],
            object_key=upload["object_key"],
            declared_mime_type=upload["declared_mime_type"],
            declared_size=int(upload["declared_size"]),
            expected_checksum_sha256=upload["expected_checksum_sha256"],
            original_name=upload["original_name"],
        )


async def _upload_derived_files(
    *,
    object_store: ObjectStore,
    snapshot: ValidationSnapshot,
    inspection: MediaInspection,
) -> tuple[DerivedFile, ...]:
    outputs: list[DerivedFile] = []
    if inspection.sanitized_svg_path is not None:
        outputs.append(
            await _upload_one(
                object_store=object_store,
                snapshot=snapshot,
                path=inspection.sanitized_svg_path,
                variant="sanitized",
                preview_kind=None,
                mime_type="image/svg+xml",
                width=inspection.width,
                height=inspection.height,
            )
        )
    for preview in inspection.previews:
        outputs.append(
            await _upload_preview(
                object_store=object_store,
                snapshot=snapshot,
                preview=preview,
            )
        )
    return tuple(outputs)


async def _upload_preview(
    *,
    object_store: ObjectStore,
    snapshot: ValidationSnapshot,
    preview: PreviewOutput,
) -> DerivedFile:
    return await _upload_one(
        object_store=object_store,
        snapshot=snapshot,
        path=preview.path,
        variant=preview.variant,
        preview_kind=preview.preview_kind,
        mime_type=preview.mime_type,
        width=preview.width,
        height=preview.height,
    )


async def _upload_one(
    *,
    object_store: ObjectStore,
    snapshot: ValidationSnapshot,
    path: str,
    variant: str,
    preview_kind: str | None,
    mime_type: str,
    width: int | None,
    height: int | None,
) -> DerivedFile:
    file_id = new_uuid7()
    object_key = asset_object_key(
        organization_id=str(snapshot.organization_id),
        project_id=str(snapshot.project_id),
        asset_id=str(snapshot.asset_id),
        variant=variant,
        file_id=str(file_id),
    )
    checksum_hex = sha256_path(path)
    head = await object_store.upload_from_path(
        bucket=snapshot.bucket,
        object_key=object_key,
        path=path,
        content_type=mime_type,
        checksum_sha256_b64=sha256_hex_to_base64(checksum_hex),
    )
    if head.content_length != os.path.getsize(path):
        raise ValidationRejected("DERIVED_UPLOAD_SIZE_MISMATCH")
    return DerivedFile(
        id=file_id,
        variant=variant,
        preview_kind=preview_kind,
        bucket=snapshot.bucket,
        object_key=object_key,
        checksum_sha256=checksum_hex,
        mime_type=mime_type,
        byte_size=head.content_length,
        width=width,
        height=height,
    )


async def _finalize_success(
    *,
    settings: AssetWorkerSettings,
    snapshot: ValidationSnapshot,
    inspection: MediaInspection,
    full_checksum: str,
    scanner_status: str,
    derived: tuple[DerivedFile, ...],
) -> None:
    connection = await asyncpg.connect(settings.asyncpg_dsn())
    try:
        async with connection.transaction():
            current = await connection.fetchrow(
                """
                SELECT status FROM asset_validation_runs
                WHERE id = $1 AND organization_id = $2
                FOR UPDATE
                """,
                snapshot.validation_run_id,
                snapshot.organization_id,
            )
            if current is None or current["status"] != "running":
                raise RuntimeError("VALIDATION_RUN_NOT_RUNNING")
            await connection.execute(
                """
                INSERT INTO asset_files (
                    id, organization_id, asset_id, variant, bucket, object_key,
                    checksum_sha256, mime_type, byte_size, width, height,
                    created_at, updated_at, version
                ) VALUES ($1,$2,$3,'original',$4,$5,$6,$7,$8,$9,$10,now(),now(),1)
                """,
                snapshot.asset_file_id,
                snapshot.organization_id,
                snapshot.asset_id,
                snapshot.bucket,
                snapshot.object_key,
                full_checksum,
                inspection.sniffed_mime_type,
                snapshot.declared_size,
                inspection.width,
                inspection.height,
            )
            for item in derived:
                await connection.execute(
                    """
                    INSERT INTO asset_files (
                        id, organization_id, asset_id, variant, bucket, object_key,
                        checksum_sha256, mime_type, byte_size, width, height,
                        created_at, updated_at, version
                    ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,now(),now(),1)
                    """,
                    item.id,
                    snapshot.organization_id,
                    snapshot.asset_id,
                    item.variant,
                    item.bucket,
                    item.object_key,
                    item.checksum_sha256,
                    item.mime_type,
                    item.byte_size,
                    item.width,
                    item.height,
                )
                if item.preview_kind is not None:
                    await connection.execute(
                        """
                        INSERT INTO asset_previews (
                            id, organization_id, asset_id, asset_file_id, preview_kind,
                            created_at, updated_at, version
                        ) VALUES ($1,$2,$3,$4,$5,now(),now(),1)
                        """,
                        new_uuid7(),
                        snapshot.organization_id,
                        snapshot.asset_id,
                        item.id,
                        item.preview_kind,
                    )
            metadata = dict(inspection.metadata)
            metadata["scanner_status"] = scanner_status
            metadata["full_checksum_sha256"] = full_checksum
            await connection.execute(
                """
                INSERT INTO asset_metadata (
                    id, organization_id, asset_id, namespace, data_json,
                    created_at, updated_at, version
                ) VALUES ($1,$2,$3,'media',$4::jsonb,now(),now(),1)
                ON CONFLICT (asset_id, namespace)
                DO UPDATE SET data_json = EXCLUDED.data_json,
                              updated_at = now(),
                              version = asset_metadata.version + 1
                """,
                new_uuid7(),
                snapshot.organization_id,
                snapshot.asset_id,
                json.dumps(metadata, ensure_ascii=False, separators=(",", ":")),
            )
            await connection.execute(
                """
                UPDATE asset_validation_runs
                SET status = 'succeeded', scanner_status = $2,
                    sniffed_mime_type = $3, full_checksum_sha256 = $4,
                    failure_code = NULL, metadata_json = $5::jsonb,
                    completed_at = now(), updated_at = now(), version = version + 1
                WHERE id = $1
                """,
                snapshot.validation_run_id,
                scanner_status,
                inspection.sniffed_mime_type,
                full_checksum,
                json.dumps(metadata, ensure_ascii=False, separators=(",", ":")),
            )
            await connection.execute(
                """
                UPDATE assets
                SET status = 'ready', kind = $2, rejection_code = NULL,
                    updated_at = now(), version = version + 1
                WHERE id = $1 AND organization_id = $3 AND status = 'scanning'
                """,
                snapshot.asset_id,
                inspection.kind,
                snapshot.organization_id,
            )
            await _insert_event(
                connection,
                organization_id=snapshot.organization_id,
                asset_id=snapshot.asset_id,
                name="asset.ready",
                payload={
                    "project_id": str(snapshot.project_id),
                    "validation_run_id": str(snapshot.validation_run_id),
                    "mime_type": inspection.sniffed_mime_type,
                    "scanner_status": scanner_status,
                },
            )
    finally:
        await connection.close()


async def _finalize_failure(
    *,
    settings: AssetWorkerSettings,
    snapshot: ValidationSnapshot,
    status: str,
    scanner_status: str | None,
    full_checksum: str | None,
    failure_code: str,
) -> None:
    connection = await asyncpg.connect(settings.asyncpg_dsn())
    try:
        async with connection.transaction():
            await connection.execute(
                """
                UPDATE asset_validation_runs
                SET status = $2, scanner_status = $3,
                    full_checksum_sha256 = $4, failure_code = $5,
                    completed_at = now(), updated_at = now(), version = version + 1
                WHERE id = $1 AND status = 'running'
                """,
                snapshot.validation_run_id,
                status,
                scanner_status,
                full_checksum,
                failure_code,
            )
            await connection.execute(
                """
                UPDATE assets
                SET status = 'rejected', rejection_code = $2,
                    updated_at = now(), version = version + 1
                WHERE id = $1 AND organization_id = $3
                """,
                snapshot.asset_id,
                failure_code,
                snapshot.organization_id,
            )
            await _insert_event(
                connection,
                organization_id=snapshot.organization_id,
                asset_id=snapshot.asset_id,
                name="asset.rejected",
                payload={
                    "project_id": str(snapshot.project_id),
                    "validation_run_id": str(snapshot.validation_run_id),
                    "failure_code": failure_code,
                    "scanner_status": scanner_status,
                },
            )
    finally:
        await connection.close()


async def _insert_event(
    connection: asyncpg.Connection,
    *,
    organization_id: UUID,
    asset_id: UUID,
    name: str,
    payload: dict[str, Any],
) -> None:
    await connection.execute(
        """
        INSERT INTO outbox_events (
            id, organization_id, event_name, aggregate_type, aggregate_id,
            schema_version, payload_json, created_at
        ) VALUES ($1,$2,$3,'asset',$4,1,$5::jsonb,now())
        """,
        new_uuid7(),
        organization_id,
        name,
        asset_id,
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
    )
