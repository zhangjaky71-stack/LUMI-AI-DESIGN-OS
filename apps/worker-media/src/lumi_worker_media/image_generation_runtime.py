from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import asyncpg
from lumi_image_generation.inmemory import StaticReferenceAuthorizer
from lumi_image_generation.model import GenerationJob, ImageGenerationSpec
from lumi_image_generation.pipeline import ImageGenerationPipeline
from lumi_image_generation.validation import CompositeGenerationValidator

from .image_gateway_runtime import HostedImageModelGatewayAdapter, S3ProviderOutputFetcher
from .image_generation_artifacts import PostgresArtifactCandidateAdapter
from .image_generation_codec import decode_spec
from .image_generation_ports import (
    PostgresGenerationCostObserver,
    PostgresGenerationEventSink,
    PostgresReferenceAuthorizer,
    S3GeneratedImageStore,
)
from .image_generation_repository import PostgresGenerationRepository
from .queue_contracts import JobMessage

_TASK_INPUT_SCHEMA_VERSION = 1
_JOB_KIND = "image.transform"


class HostedImageGenerationRuntime:
    """Production composition root for NODE-46 image generation."""

    def __init__(
        self,
        *,
        database_dsn: str,
        asset_bucket: str,
        repository: PostgresGenerationRepository,
        reference_resolver: PostgresReferenceAuthorizer,
        gateway: HostedImageModelGatewayAdapter,
        output_fetcher: S3ProviderOutputFetcher,
        storage: S3GeneratedImageStore,
        artifacts: PostgresArtifactCandidateAdapter,
        costs: PostgresGenerationCostObserver,
        events: PostgresGenerationEventSink,
    ) -> None:
        self.database_dsn = _asyncpg_dsn(database_dsn)
        self.asset_bucket = asset_bucket
        self.repository = repository
        self.reference_resolver = reference_resolver
        self.gateway = gateway
        self.output_fetcher = output_fetcher
        self.storage = storage
        self.artifacts = artifacts
        self.costs = costs
        self.events = events

    @classmethod
    def from_env(cls) -> HostedImageGenerationRuntime:
        database_dsn = _required_env("LUMI_DATABASE_URL", max_length=8192)
        asset_bucket = _required_env("LUMI_S3_BUCKET", max_length=255)
        return cls(
            database_dsn=database_dsn,
            asset_bucket=asset_bucket,
            repository=PostgresGenerationRepository(database_dsn),
            reference_resolver=PostgresReferenceAuthorizer(database_dsn),
            gateway=HostedImageModelGatewayAdapter.from_env(),
            output_fetcher=S3ProviderOutputFetcher.from_env(),
            storage=S3GeneratedImageStore.from_env(),
            artifacts=PostgresArtifactCandidateAdapter(database_dsn, bucket=asset_bucket),
            costs=PostgresGenerationCostObserver(database_dsn),
            events=PostgresGenerationEventSink(database_dsn),
        )

    async def execute(self, message: JobMessage) -> dict[str, Any]:
        spec = await self._load_spec(message)
        authorized = await self.reference_resolver.authorize(spec, spec.references)
        authorizer = StaticReferenceAuthorizer(
            {(item.asset_id, item.asset_version): item for item in authorized}
        )
        pipeline = ImageGenerationPipeline(
            repository=self.repository,
            references=authorizer,
            gateway=self.gateway,
            output_fetcher=self.output_fetcher,
            storage=self.storage,
            validator=CompositeGenerationValidator(),
            artifacts=self.artifacts,
            costs=self.costs,
            events=self.events,
        )
        existing = await self.repository.get_by_operation(
            spec.organization_id,
            spec.operation_id,
        )
        now = datetime.now(UTC).isoformat()
        if existing is not None and existing.status == "PROVIDER_PENDING":
            job = await pipeline.resume_pending(
                organization_id=spec.organization_id,
                generation_id=existing.generation_id,
                completed_at=now,
            )
        else:
            job = await pipeline.start(spec, created_at=now)
        return _task_output(job)

    async def _load_spec(self, message: JobMessage) -> ImageGenerationSpec:
        connection = await asyncpg.connect(self.database_dsn)
        try:
            row = await connection.fetchrow(
                """
                SELECT type, input_json
                FROM tasks
                WHERE id=$1 AND organization_id=$2 AND project_id=$3
                """,
                message.job_id,
                message.organization_id,
                message.project_id,
            )
        finally:
            await connection.close()
        if row is None:
            raise RuntimeError("IMAGE_GENERATION_TASK_NOT_FOUND")
        if row["type"] != _JOB_KIND:
            raise RuntimeError("IMAGE_GENERATION_TASK_TYPE_MISMATCH")
        input_payload = _json_object(row["input_json"])
        if input_payload.get("schema_version") != _TASK_INPUT_SCHEMA_VERSION:
            raise RuntimeError("IMAGE_GENERATION_TASK_INPUT_SCHEMA_UNSUPPORTED")
        if input_payload.get("job_kind") != _JOB_KIND:
            raise RuntimeError("IMAGE_GENERATION_TASK_INPUT_KIND_MISMATCH")
        raw_spec = input_payload.get("image_generation_spec")
        if not isinstance(raw_spec, dict):
            raise RuntimeError("IMAGE_GENERATION_TASK_SPEC_MISSING")
        spec = decode_spec(raw_spec)
        if UUID(spec.organization_id) != message.organization_id:
            raise RuntimeError("IMAGE_GENERATION_TASK_ORGANIZATION_MISMATCH")
        if UUID(spec.project_id) != message.project_id:
            raise RuntimeError("IMAGE_GENERATION_TASK_PROJECT_MISMATCH")
        if UUID(spec.task_id) != message.job_id:
            raise RuntimeError("IMAGE_GENERATION_TASK_ID_MISMATCH")
        if message.operation_id is None or UUID(spec.operation_id) != message.operation_id:
            raise RuntimeError("IMAGE_GENERATION_TASK_OPERATION_MISMATCH")
        return spec


def encode_task_input(spec: ImageGenerationSpec) -> dict[str, Any]:
    """Canonical task input envelope used by API/control-plane producers."""
    from .image_generation_codec import encode_spec

    return {
        "schema_version": _TASK_INPUT_SCHEMA_VERSION,
        "job_kind": _JOB_KIND,
        "image_generation_spec": encode_spec(spec),
    }


def _task_output(job: GenerationJob) -> dict[str, Any]:
    return {
        "generation_id": job.generation_id,
        "status": job.status,
        "operation_id": job.operation_id,
        "candidate_count": len(job.candidates),
        "artifacts": [
            {
                "candidate_id": candidate.candidate_id,
                "status": candidate.status,
                "artifact_id": candidate.artifact_id,
                "artifact_version_id": candidate.artifact_version_id,
                "error_code": candidate.error_code,
            }
            for candidate in job.candidates
        ],
    }


def _json_object(value: object) -> dict[str, Any]:
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise RuntimeError("IMAGE_GENERATION_TASK_INPUT_INVALID")
    return value


def _required_env(name: str, *, max_length: int) -> str:
    value = os.getenv(name, "")
    if not value or len(value) > max_length or "\x00" in value:
        raise RuntimeError(f"{name}_REQUIRED")
    return value


def _asyncpg_dsn(database_dsn: str) -> str:
    if database_dsn.startswith("postgresql+asyncpg://"):
        return "postgresql://" + database_dsn[len("postgresql+asyncpg://") :]
    if database_dsn.startswith("postgresql://"):
        return database_dsn
    raise ValueError("GENERATION_DATABASE_URL_MUST_USE_POSTGRESQL")
