from __future__ import annotations

import json
from decimal import Decimal
from uuid import UUID, uuid5

import asyncpg
from lumi_video_generation.model import (
    CompiledShot,
    FinalVideoProvenance,
    RenderedVideo,
    ShotProvenance,
    ShotValidationReport,
    StoredVideoClip,
    VideoTaskSpec,
)


class PostgresVideoArtifactAdapter:
    """Persist NODE-48 outputs into the canonical Artifact Engine tables."""

    def __init__(self, database_dsn: str, *, bucket: str) -> None:
        self.dsn = _asyncpg_dsn(database_dsn)
        if not bucket or bucket != bucket.strip() or "/" in bucket:
            raise ValueError("VIDEO_ARTIFACT_BUCKET_INVALID")
        self.bucket = bucket

    async def create_clip(
        self,
        *,
        spec: VideoTaskSpec,
        shot: CompiledShot,
        clip: StoredVideoClip,
        provenance: ShotProvenance,
        validation: ShotValidationReport,
        continuity_parent_version_ids: tuple[str, ...],
    ) -> str:
        org_id = UUID(spec.organization_id)
        project_id = UUID(spec.project_id)
        task_id = UUID(spec.task_id)
        operation_id = UUID(spec.operation_id)
        artifact_id = uuid5(
            org_id,
            f"node48-video-clip:{provenance.video_job_id}:{shot.shot.shot_id}:{provenance.paid_operation_id}",
        )
        version_id = uuid5(artifact_id, f"version:{provenance.snapshot_id}")
        branch_id = uuid5(artifact_id, "branch:main")
        file_id = uuid5(version_id, f"file:{clip.checksum_sha256}")
        provenance_id = uuid5(version_id, f"provenance:{provenance.snapshot_id}")
        status = "ready" if validation.decision == "PASS" else "rejected"
        metadata = {
            "node": "NODE-48",
            "scope": "SHOT",
            "video_job_id": provenance.video_job_id,
            "shot_id": shot.shot.shot_id,
            "paid_operation_id": provenance.paid_operation_id,
            "poster_frame_ref": clip.poster_frame_ref,
            "tail_frame_ref": clip.tail_frame_ref,
            "duration_ms": clip.duration_ms,
            "width": clip.width,
            "height": clip.height,
            "validation_decision": validation.decision,
            "identity_validation_snapshot_id": validation.identity_validation_snapshot_id,
            "brand_validation_snapshot_id": validation.brand_validation_snapshot_id,
        }
        provenance_metadata = {
            "video_job_id": provenance.video_job_id,
            "shot_id": provenance.shot_id,
            "paid_operation_id": provenance.paid_operation_id,
            "storyboard_hash": provenance.storyboard_hash,
            "prompt_hash": provenance.prompt_hash,
            "source_refs": list(provenance.source_refs),
            "continuity_refs": list(provenance.continuity_refs),
            "provider": provenance.provider,
            "model": provenance.model,
            "provider_request_id": provenance.provider_request_id,
            "routing_reason_codes": list(provenance.routing_reason_codes),
            "pricing_snapshot_id": provenance.pricing_snapshot_id,
            "cost_usd": _decimal_text(provenance.cost_usd),
            "cost_confidence": provenance.cost_confidence,
            "brand_rule_set_version": provenance.brand_rule_set_version,
            "identity_validation_snapshot_id": provenance.identity_validation_snapshot_id,
            "code_git_sha": provenance.code_git_sha,
        }
        parents = tuple(dict.fromkeys(continuity_parent_version_ids))
        connection = await asyncpg.connect(self.dsn)
        try:
            async with connection.transaction():
                await _lock(connection, artifact_id)
                await _ensure_artifact(
                    connection,
                    artifact_id=artifact_id,
                    organization_id=org_id,
                    project_id=project_id,
                    kind="VIDEO",
                    title=f"Video shot {shot.shot.shot_id} attempt",
                    metadata=metadata,
                )
                await _ensure_branch(
                    connection,
                    branch_id=branch_id,
                    organization_id=org_id,
                    project_id=project_id,
                    artifact_id=artifact_id,
                )
                await _ensure_version(
                    connection,
                    version_id=version_id,
                    organization_id=org_id,
                    project_id=project_id,
                    artifact_id=artifact_id,
                    branch_id=branch_id,
                    status=status,
                    content_hash=clip.checksum_sha256,
                    metadata=metadata,
                    created_by_id=task_id,
                )
                await _ensure_file(
                    connection,
                    file_id=file_id,
                    organization_id=org_id,
                    artifact_version_id=version_id,
                    bucket=self.bucket,
                    object_key=clip.storage_key,
                    checksum=clip.checksum_sha256,
                    mime_type=clip.mime_type,
                )
                await _ensure_provenance(
                    connection,
                    provenance_id=provenance_id,
                    organization_id=org_id,
                    artifact_version_id=version_id,
                    source_id=operation_id,
                    operation="video.generate.shot",
                    metadata=provenance_metadata,
                )
                for index, parent in enumerate(parents):
                    await _ensure_edge(
                        connection,
                        edge_id=uuid5(version_id, f"reference:{index}:{parent}"),
                        organization_id=org_id,
                        from_version_id=_uuid(parent, "VIDEO_PARENT_ARTIFACT_VERSION_INVALID"),
                        to_version_id=version_id,
                        edge_type="REFERENCE_USED",
                        metadata={"shot_id": shot.shot.shot_id, "ordinal": index + 1},
                    )
                await _set_branch_head(
                    connection,
                    branch_id=branch_id,
                    organization_id=org_id,
                    artifact_id=artifact_id,
                    version_id=version_id,
                )
        finally:
            await connection.close()
        return str(version_id)

    async def create_final(
        self,
        *,
        spec: VideoTaskSpec,
        rendered: RenderedVideo,
        provenance: FinalVideoProvenance,
        validation: ShotValidationReport,
        clip_artifact_version_ids: tuple[str, ...],
    ) -> str:
        org_id = UUID(spec.organization_id)
        project_id = UUID(spec.project_id)
        task_id = UUID(spec.task_id)
        operation_id = UUID(spec.operation_id)
        artifact_id = uuid5(org_id, f"node48-video-final:{provenance.video_job_id}")
        version_id = uuid5(artifact_id, f"version:{provenance.snapshot_id}")
        branch_id = uuid5(artifact_id, "branch:main")
        file_id = uuid5(version_id, f"file:{rendered.video.checksum_sha256}")
        provenance_id = uuid5(version_id, f"provenance:{provenance.snapshot_id}")
        status = "ready" if validation.decision == "PASS" else "rejected"
        metadata = {
            "node": "NODE-48",
            "scope": "FINAL",
            "video_job_id": provenance.video_job_id,
            "storyboard_hash": provenance.storyboard_hash,
            "timeline_hash": provenance.timeline_hash,
            "duration_ms": rendered.video.duration_ms,
            "width": rendered.video.width,
            "height": rendered.video.height,
            "validation_decision": validation.decision,
            "brand_rule_set_version": provenance.brand_rule_set_version,
        }
        provenance_metadata = {
            "video_job_id": provenance.video_job_id,
            "storyboard_hash": provenance.storyboard_hash,
            "timeline_hash": provenance.timeline_hash,
            "clip_artifact_version_ids": list(provenance.clip_artifact_version_ids),
            "code_git_sha": provenance.code_git_sha,
            "brand_rule_set_version": provenance.brand_rule_set_version,
        }
        connection = await asyncpg.connect(self.dsn)
        try:
            async with connection.transaction():
                await _lock(connection, artifact_id)
                await _ensure_artifact(
                    connection,
                    artifact_id=artifact_id,
                    organization_id=org_id,
                    project_id=project_id,
                    kind="VIDEO",
                    title="Final generated video",
                    metadata=metadata,
                )
                await _ensure_branch(
                    connection,
                    branch_id=branch_id,
                    organization_id=org_id,
                    project_id=project_id,
                    artifact_id=artifact_id,
                )
                await _ensure_version(
                    connection,
                    version_id=version_id,
                    organization_id=org_id,
                    project_id=project_id,
                    artifact_id=artifact_id,
                    branch_id=branch_id,
                    status=status,
                    content_hash=rendered.video.checksum_sha256,
                    metadata=metadata,
                    created_by_id=task_id,
                )
                await _ensure_file(
                    connection,
                    file_id=file_id,
                    organization_id=org_id,
                    artifact_version_id=version_id,
                    bucket=self.bucket,
                    object_key=rendered.video.storage_key,
                    checksum=rendered.video.checksum_sha256,
                    mime_type=rendered.video.mime_type,
                )
                await _ensure_provenance(
                    connection,
                    provenance_id=provenance_id,
                    organization_id=org_id,
                    artifact_version_id=version_id,
                    source_id=operation_id,
                    operation="video.generate.final",
                    metadata=provenance_metadata,
                )
                for index, clip_version in enumerate(dict.fromkeys(clip_artifact_version_ids)):
                    await _ensure_edge(
                        connection,
                        edge_id=uuid5(version_id, f"composed:{index}:{clip_version}"),
                        organization_id=org_id,
                        from_version_id=_uuid(
                            clip_version, "VIDEO_CLIP_ARTIFACT_VERSION_INVALID"
                        ),
                        to_version_id=version_id,
                        edge_type="COMPOSED_FROM",
                        metadata={"ordinal": index + 1},
                    )
                await _set_branch_head(
                    connection,
                    branch_id=branch_id,
                    organization_id=org_id,
                    artifact_id=artifact_id,
                    version_id=version_id,
                )
        finally:
            await connection.close()
        return str(version_id)


async def _lock(connection: asyncpg.Connection, artifact_id: UUID) -> None:
    await connection.execute(
        "SELECT pg_advisory_xact_lock($1)",
        int.from_bytes(artifact_id.bytes[:8], "big", signed=True),
    )


async def _ensure_artifact(
    connection: asyncpg.Connection,
    *,
    artifact_id: UUID,
    organization_id: UUID,
    project_id: UUID,
    kind: str,
    title: str,
    metadata: dict[str, object],
) -> None:
    await connection.execute(
        """
        INSERT INTO artifacts (
            id, organization_id, project_id, kind, title, metadata_json,
            created_at, updated_at, version
        ) VALUES ($1,$2,$3,$4,$5,$6::jsonb,now(),now(),1)
        ON CONFLICT (id) DO NOTHING
        """,
        artifact_id,
        organization_id,
        project_id,
        kind,
        title,
        _json(metadata),
    )
    row = await connection.fetchrow(
        "SELECT organization_id, project_id, kind FROM artifacts WHERE id=$1",
        artifact_id,
    )
    if row is None or (
        row["organization_id"] != organization_id
        or row["project_id"] != project_id
        or row["kind"] != kind
    ):
        raise RuntimeError("VIDEO_ARTIFACT_IDENTITY_CONFLICT")


async def _ensure_branch(
    connection: asyncpg.Connection,
    *,
    branch_id: UUID,
    organization_id: UUID,
    project_id: UUID,
    artifact_id: UUID,
) -> None:
    await connection.execute(
        """
        INSERT INTO artifact_branches (
            id, organization_id, project_id, artifact_id, name,
            head_version_id, created_at, updated_at, version
        ) VALUES ($1,$2,$3,$4,'main',NULL,now(),now(),1)
        ON CONFLICT (id) DO NOTHING
        """,
        branch_id,
        organization_id,
        project_id,
        artifact_id,
    )


async def _ensure_version(
    connection: asyncpg.Connection,
    *,
    version_id: UUID,
    organization_id: UUID,
    project_id: UUID,
    artifact_id: UUID,
    branch_id: UUID,
    status: str,
    content_hash: str,
    metadata: dict[str, object],
    created_by_id: UUID,
) -> None:
    await connection.execute(
        """
        INSERT INTO artifact_versions (
            id, organization_id, project_id, artifact_id, branch_id,
            parent_version_id, version_number, status, content_hash,
            metadata_json, quality_score, created_by_type, created_by_id, created_at
        ) VALUES ($1,$2,$3,$4,$5,NULL,1,$6,$7,$8::jsonb,NULL,'agent',$9,now())
        ON CONFLICT (id) DO NOTHING
        """,
        version_id,
        organization_id,
        project_id,
        artifact_id,
        branch_id,
        status,
        content_hash,
        _json(metadata),
        created_by_id,
    )
    row = await connection.fetchrow(
        "SELECT status, content_hash FROM artifact_versions WHERE id=$1",
        version_id,
    )
    if row is None or row["status"] != status or row["content_hash"] != content_hash:
        raise RuntimeError("VIDEO_ARTIFACT_VERSION_CONFLICT")


async def _ensure_file(
    connection: asyncpg.Connection,
    *,
    file_id: UUID,
    organization_id: UUID,
    artifact_version_id: UUID,
    bucket: str,
    object_key: str,
    checksum: str,
    mime_type: str,
) -> None:
    if mime_type != "video/mp4":
        raise ValueError("VIDEO_ARTIFACT_MIME_UNSUPPORTED")
    await connection.execute(
        """
        INSERT INTO artifact_files (
            id, organization_id, artifact_version_id, format, bucket,
            object_key, checksum_sha256, mime_type, created_at
        ) VALUES ($1,$2,$3,'MP4',$4,$5,$6,$7,now())
        ON CONFLICT (id) DO NOTHING
        """,
        file_id,
        organization_id,
        artifact_version_id,
        bucket,
        object_key,
        checksum,
        mime_type,
    )


async def _ensure_provenance(
    connection: asyncpg.Connection,
    *,
    provenance_id: UUID,
    organization_id: UUID,
    artifact_version_id: UUID,
    source_id: UUID,
    operation: str,
    metadata: dict[str, object],
) -> None:
    await connection.execute(
        """
        INSERT INTO artifact_provenance (
            id, organization_id, artifact_version_id, source_type,
            source_id, operation, metadata_json, created_at
        ) VALUES ($1,$2,$3,'generation',$4,$5,$6::jsonb,now())
        ON CONFLICT (id) DO NOTHING
        """,
        provenance_id,
        organization_id,
        artifact_version_id,
        source_id,
        operation,
        _json(metadata),
    )


async def _ensure_edge(
    connection: asyncpg.Connection,
    *,
    edge_id: UUID,
    organization_id: UUID,
    from_version_id: UUID,
    to_version_id: UUID,
    edge_type: str,
    metadata: dict[str, object],
) -> None:
    parent = await connection.fetchval(
        "SELECT id FROM artifact_versions WHERE id=$1 AND organization_id=$2",
        from_version_id,
        organization_id,
    )
    if parent is None:
        raise RuntimeError("VIDEO_ARTIFACT_PARENT_NOT_FOUND")
    await connection.execute(
        """
        INSERT INTO artifact_edges (
            id, organization_id, from_artifact_version_id,
            to_artifact_version_id, edge_type, metadata_json, created_at
        ) VALUES ($1,$2,$3,$4,$5,$6::jsonb,now())
        ON CONFLICT (id) DO NOTHING
        """,
        edge_id,
        organization_id,
        from_version_id,
        to_version_id,
        edge_type,
        _json(metadata),
    )


async def _set_branch_head(
    connection: asyncpg.Connection,
    *,
    branch_id: UUID,
    organization_id: UUID,
    artifact_id: UUID,
    version_id: UUID,
) -> None:
    await connection.execute(
        """
        UPDATE artifact_branches
        SET head_version_id=$2, updated_at=now(), version=version+1
        WHERE id=$1 AND organization_id=$3 AND artifact_id=$4
          AND (head_version_id IS NULL OR head_version_id=$2)
        """,
        branch_id,
        version_id,
        organization_id,
        artifact_id,
    )
    head = await connection.fetchval(
        "SELECT head_version_id FROM artifact_branches WHERE id=$1",
        branch_id,
    )
    if head != version_id:
        raise RuntimeError("VIDEO_ARTIFACT_BRANCH_HEAD_CONFLICT")


def _decimal_text(value: Decimal | None) -> str | None:
    if value is None:
        return None
    if not value.is_finite():
        raise ValueError("VIDEO_ARTIFACT_COST_NON_FINITE")
    return format(value, "f")


def _uuid(value: str, error: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as exc:
        raise ValueError(error) from exc


def _json(value: dict[str, object]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _asyncpg_dsn(database_dsn: str) -> str:
    if database_dsn.startswith("postgresql+asyncpg://"):
        return "postgresql://" + database_dsn[len("postgresql+asyncpg://") :]
    if database_dsn.startswith("postgresql://"):
        return database_dsn
    raise ValueError("VIDEO_DATABASE_URL_MUST_USE_POSTGRESQL")
