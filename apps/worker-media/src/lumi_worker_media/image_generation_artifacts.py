from __future__ import annotations

import json
from decimal import Decimal
from uuid import UUID, uuid5

import asyncpg
from lumi_image_generation.hashing import constraint_snapshot_hash
from lumi_image_generation.model import (
    GenerationCandidate,
    GenerationProvenanceSnapshot,
    ImageGenerationSpec,
    StoredImage,
    ValidationBundle,
)
from lumi_image_generation.ports import ArtifactCandidateResult


class PostgresArtifactCandidateAdapter:
    """Creates one immutable raster artifact/version per generated candidate."""

    def __init__(self, database_dsn: str, *, bucket: str) -> None:
        self.dsn = _asyncpg_dsn(database_dsn)
        if not bucket or "/" in bucket or bucket != bucket.strip():
            raise ValueError("GENERATION_ARTIFACT_BUCKET_INVALID")
        self.bucket = bucket

    async def create_candidate(
        self,
        *,
        spec: ImageGenerationSpec,
        candidate: GenerationCandidate,
        stored: StoredImage,
        provenance: GenerationProvenanceSnapshot,
        validation: ValidationBundle,
    ) -> ArtifactCandidateResult:
        if not stored.storage_key.startswith("generated/v1/"):
            raise ValueError("GENERATION_ARTIFACT_REQUIRES_DURABLE_GENERATED_OBJECT")
        org_id = UUID(spec.organization_id)
        project_id = UUID(spec.project_id)
        task_id = UUID(spec.task_id)
        operation_id = UUID(spec.operation_id)
        artifact_id = uuid5(org_id, f"node46-artifact:{candidate.candidate_id}")
        branch_id = uuid5(artifact_id, "branch:main")
        version_id = uuid5(artifact_id, f"version:{provenance.snapshot_id}")
        file_id = uuid5(version_id, f"file:{stored.checksum_sha256}")
        provenance_id = uuid5(version_id, f"provenance:{provenance.snapshot_id}")
        target_status = "rejected" if validation.hard_failed else "ready"
        file_format = _file_format(stored.mime_type)
        metadata = {
            "node": "NODE-46",
            "generation_id": provenance.generation_id,
            "candidate_id": candidate.candidate_id,
            "variant_index": candidate.variant_index,
            "generation_provenance_snapshot_id": provenance.snapshot_id,
            "constraint_snapshot_hash": constraint_snapshot_hash(spec),
            "brand_rule_set_version": spec.brand_rule_set_version,
            "identity_validation_snapshot_id": validation.identity_validation_snapshot_id,
            "width": stored.width,
            "height": stored.height,
            "size_bytes": stored.size_bytes,
        }
        provenance_metadata = {
            "generation_id": provenance.generation_id,
            "provider": provenance.provider,
            "model": provenance.model,
            "model_revision": provenance.model_revision,
            "provider_request_id": provenance.provider_request_id,
            "prompt_hash": provenance.prompt_hash,
            "prompt_template_version": provenance.prompt_template_version,
            "prompt_compilation_ref": provenance.prompt_compilation_ref,
            "reference_asset_refs": list(provenance.reference_asset_refs),
            "seed": provenance.seed,
            "routing_reason_codes": list(provenance.routing_reason_codes),
            "pricing_snapshot_id": provenance.pricing_snapshot_id,
            "cost_usd": (
                format(provenance.cost_usd, "f")
                if isinstance(provenance.cost_usd, Decimal)
                else None
            ),
            "cost_confidence": provenance.cost_confidence,
            "code_git_sha": provenance.code_git_sha,
            "recipe_version": provenance.recipe_version,
            "skill_versions": dict(provenance.skill_versions),
            "safety_metadata": _json_safe(dict(provenance.safety_metadata)),
        }

        connection = await asyncpg.connect(self.dsn)
        try:
            async with connection.transaction():
                await connection.execute(
                    "SELECT pg_advisory_xact_lock($1)",
                    _lock_key(artifact_id),
                )
                await connection.execute(
                    """
                    INSERT INTO artifacts (
                        id, organization_id, project_id, kind, title, metadata_json,
                        created_at, updated_at, version
                    ) VALUES (
                        $1,$2,$3,'RASTER_IMAGE',$4,$5::jsonb,now(),now(),1
                    )
                    ON CONFLICT (id) DO NOTHING
                    """,
                    artifact_id,
                    org_id,
                    project_id,
                    f"Generated image variant {candidate.variant_index}",
                    _json(metadata),
                )
                await _assert_artifact_identity(
                    connection,
                    artifact_id=artifact_id,
                    organization_id=org_id,
                    project_id=project_id,
                )
                await connection.execute(
                    """
                    INSERT INTO artifact_branches (
                        id, organization_id, project_id, artifact_id, name,
                        head_version_id, created_at, updated_at, version
                    ) VALUES ($1,$2,$3,$4,'main',NULL,now(),now(),1)
                    ON CONFLICT (id) DO NOTHING
                    """,
                    branch_id,
                    org_id,
                    project_id,
                    artifact_id,
                )
                await connection.execute(
                    """
                    INSERT INTO artifact_versions (
                        id, organization_id, project_id, artifact_id, branch_id,
                        parent_version_id, version_number, status, content_hash,
                        metadata_json, quality_score, created_by_type, created_by_id,
                        created_at
                    ) VALUES (
                        $1,$2,$3,$4,$5,NULL,1,$6,$7,$8::jsonb,NULL,'agent',$9,now()
                    )
                    ON CONFLICT (id) DO NOTHING
                    """,
                    version_id,
                    org_id,
                    project_id,
                    artifact_id,
                    branch_id,
                    target_status,
                    stored.checksum_sha256,
                    _json(metadata),
                    task_id,
                )
                version = await connection.fetchrow(
                    """
                    SELECT status, content_hash, metadata_json
                    FROM artifact_versions
                    WHERE id=$1 AND organization_id=$2 AND artifact_id=$3
                    """,
                    version_id,
                    org_id,
                    artifact_id,
                )
                if version is None:
                    raise RuntimeError("GENERATION_ARTIFACT_VERSION_NOT_FOUND")
                if version["status"] != target_status:
                    raise RuntimeError("GENERATION_ARTIFACT_VERSION_STATUS_CONFLICT")
                if version["content_hash"] != stored.checksum_sha256:
                    raise RuntimeError("GENERATION_ARTIFACT_VERSION_CONTENT_CONFLICT")
                await connection.execute(
                    """
                    INSERT INTO artifact_files (
                        id, organization_id, artifact_version_id, format, bucket,
                        object_key, checksum_sha256, mime_type, created_at
                    ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,now())
                    ON CONFLICT (id) DO NOTHING
                    """,
                    file_id,
                    org_id,
                    version_id,
                    file_format,
                    self.bucket,
                    stored.storage_key,
                    stored.checksum_sha256,
                    stored.mime_type,
                )
                file_row = await connection.fetchrow(
                    """
                    SELECT bucket, object_key, checksum_sha256, mime_type
                    FROM artifact_files
                    WHERE id=$1 AND organization_id=$2 AND artifact_version_id=$3
                    """,
                    file_id,
                    org_id,
                    version_id,
                )
                if file_row is None:
                    raise RuntimeError("GENERATION_ARTIFACT_FILE_NOT_FOUND")
                if (
                    file_row["bucket"] != self.bucket
                    or file_row["object_key"] != stored.storage_key
                    or file_row["checksum_sha256"] != stored.checksum_sha256
                    or file_row["mime_type"] != stored.mime_type
                ):
                    raise RuntimeError("GENERATION_ARTIFACT_FILE_CONFLICT")
                await connection.execute(
                    """
                    INSERT INTO artifact_provenance (
                        id, organization_id, artifact_version_id, source_type,
                        source_id, operation, metadata_json, created_at
                    ) VALUES ($1,$2,$3,'generation',$4,'image.generate',$5::jsonb,now())
                    ON CONFLICT (id) DO NOTHING
                    """,
                    provenance_id,
                    org_id,
                    version_id,
                    operation_id,
                    _json(provenance_metadata),
                )
                await connection.execute(
                    """
                    UPDATE artifact_branches
                    SET head_version_id=$2, updated_at=now(), version=version+1
                    WHERE id=$1
                      AND organization_id=$3
                      AND artifact_id=$4
                      AND (head_version_id IS NULL OR head_version_id=$2)
                    """,
                    branch_id,
                    version_id,
                    org_id,
                    artifact_id,
                )
                head = await connection.fetchval(
                    "SELECT head_version_id FROM artifact_branches WHERE id=$1",
                    branch_id,
                )
                if head != version_id:
                    raise RuntimeError("GENERATION_ARTIFACT_BRANCH_HEAD_CONFLICT")
        finally:
            await connection.close()

        return ArtifactCandidateResult(
            artifact_id=str(artifact_id),
            artifact_version_id=str(version_id),
            status=target_status.upper(),
        )


async def _assert_artifact_identity(
    connection: asyncpg.Connection,
    *,
    artifact_id: UUID,
    organization_id: UUID,
    project_id: UUID,
) -> None:
    row = await connection.fetchrow(
        "SELECT organization_id, project_id, kind FROM artifacts WHERE id=$1",
        artifact_id,
    )
    if row is None:
        raise RuntimeError("GENERATION_ARTIFACT_NOT_FOUND")
    if (
        row["organization_id"] != organization_id
        or row["project_id"] != project_id
        or row["kind"] != "RASTER_IMAGE"
    ):
        raise RuntimeError("GENERATION_ARTIFACT_IDENTITY_CONFLICT")


def _file_format(mime_type: str) -> str:
    value = {
        "image/png": "PNG",
        "image/jpeg": "JPEG",
        "image/webp": "WEBP",
    }.get(mime_type)
    if value is None:
        raise ValueError("GENERATION_ARTIFACT_FORMAT_UNSUPPORTED")
    return value


def _lock_key(value: UUID) -> int:
    return int.from_bytes(value.bytes[:8], "big", signed=True)


def _json(value: dict[str, object]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _json_safe(value: object, *, depth: int = 0) -> object:
    if depth > 16:
        raise ValueError("GENERATION_ARTIFACT_METADATA_TOO_DEEP")
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if value != value or value in {float("inf"), float("-inf")}:
            raise ValueError("GENERATION_ARTIFACT_METADATA_NON_FINITE")
        return value
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("GENERATION_ARTIFACT_METADATA_NON_FINITE")
        return format(value, "f")
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (list, tuple)):
        return [_json_safe(item, depth=depth + 1) for item in value]
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise ValueError("GENERATION_ARTIFACT_METADATA_KEY_INVALID")
        return {
            key: _json_safe(item, depth=depth + 1)
            for key, item in sorted(value.items())
        }
    raise ValueError(f"GENERATION_ARTIFACT_METADATA_INVALID:{type(value).__name__}")


def _asyncpg_dsn(database_dsn: str) -> str:
    if database_dsn.startswith("postgresql+asyncpg://"):
        return "postgresql://" + database_dsn[len("postgresql+asyncpg://") :]
    if database_dsn.startswith("postgresql://"):
        return database_dsn
    raise ValueError("GENERATION_DATABASE_URL_MUST_USE_POSTGRESQL")
