from __future__ import annotations

import json

from sqlalchemy import text

from lumi_image_generation import GenerationJob

from .postgres_codec import _dump


def save_job(repository, job: GenerationJob) -> None:
    payload = _dump(job)
    with repository._transaction():
        result = repository.session.execute(
            text("""
                INSERT INTO image_generation_jobs(
                    generation_id, organization_id, project_id, task_id, operation_id,
                    semantic_hash, status, requested_variants, selected_variants,
                    estimated_cost_per_variant, job_json, created_at, updated_at, completed_at
                ) VALUES (
                    :generation_id, :organization_id, :project_id, :task_id, :operation_id,
                    :semantic_hash, :status, :requested_variants, :selected_variants,
                    :estimated_cost, CAST(:job_json AS jsonb), CAST(:created_at AS timestamptz),
                    CAST(:updated_at AS timestamptz), CAST(:completed_at AS timestamptz)
                )
                ON CONFLICT (organization_id, operation_id) DO UPDATE SET
                    status=EXCLUDED.status,
                    requested_variants=EXCLUDED.requested_variants,
                    selected_variants=EXCLUDED.selected_variants,
                    estimated_cost_per_variant=EXCLUDED.estimated_cost_per_variant,
                    job_json=EXCLUDED.job_json,
                    updated_at=EXCLUDED.updated_at,
                    completed_at=EXCLUDED.completed_at
                WHERE image_generation_jobs.semantic_hash=EXCLUDED.semantic_hash
            """),
            {
                "generation_id": job.generation_id,
                "organization_id": job.organization_id,
                "project_id": job.project_id,
                "task_id": job.task_id,
                "operation_id": job.operation_id,
                "semantic_hash": job.semantic_hash,
                "status": job.status.value,
                "requested_variants": job.variant_decision.requested_count,
                "selected_variants": job.variant_decision.selected_count,
                "estimated_cost": job.variant_decision.estimated_cost_per_variant_usd,
                "job_json": payload,
                "created_at": job.created_at,
                "updated_at": job.updated_at,
                "completed_at": job.completed_at,
            },
        )
        if result.rowcount == 0:
            raise OperationSemanticConflict("GENERATION_OPERATION_SEMANTIC_CONFLICT")
        for candidate in job.candidates:
            repository.session.execute(
                text("""
                    INSERT INTO image_generation_candidates(
                        candidate_id, organization_id, generation_id, variant_index,
                        variant_operation_id, status, provider, model, model_revision,
                        registry_snapshot_id, provider_request_id, bucket, storage_key,
                        checksum_sha256, mime_type, width, height, size_bytes,
                        artifact_id, artifact_version_id, validation_json,
                        provenance_snapshot_id, cost_amount, cost_confidence,
                        pricing_snapshot_id, routing_reason_codes_json, error_code, updated_at
                    ) VALUES (
                        :candidate_id, :organization_id, :generation_id, :variant_index,
                        :variant_operation_id, :status, :provider, :model, :model_revision,
                        :registry_snapshot_id, :provider_request_id, :bucket, :storage_key,
                        :checksum, :mime_type, :width, :height, :size_bytes,
                        :artifact_id, :artifact_version_id, CAST(:validation AS jsonb),
                        :provenance_snapshot_id, :cost_amount, :cost_confidence,
                        :pricing_snapshot_id, CAST(:routing AS jsonb), :error_code,
                        CAST(:updated_at AS timestamptz)
                    )
                    ON CONFLICT (candidate_id) DO UPDATE SET
                        status=EXCLUDED.status,
                        provider=EXCLUDED.provider,
                        model=EXCLUDED.model,
                        model_revision=EXCLUDED.model_revision,
                        registry_snapshot_id=EXCLUDED.registry_snapshot_id,
                        provider_request_id=EXCLUDED.provider_request_id,
                        bucket=EXCLUDED.bucket,
                        storage_key=EXCLUDED.storage_key,
                        checksum_sha256=EXCLUDED.checksum_sha256,
                        mime_type=EXCLUDED.mime_type,
                        width=EXCLUDED.width,
                        height=EXCLUDED.height,
                        size_bytes=EXCLUDED.size_bytes,
                        artifact_id=EXCLUDED.artifact_id,
                        artifact_version_id=EXCLUDED.artifact_version_id,
                        validation_json=EXCLUDED.validation_json,
                        provenance_snapshot_id=EXCLUDED.provenance_snapshot_id,
                        cost_amount=EXCLUDED.cost_amount,
                        cost_confidence=EXCLUDED.cost_confidence,
                        pricing_snapshot_id=EXCLUDED.pricing_snapshot_id,
                        routing_reason_codes_json=EXCLUDED.routing_reason_codes_json,
                        error_code=EXCLUDED.error_code,
                        updated_at=EXCLUDED.updated_at
                    WHERE image_generation_candidates.organization_id=EXCLUDED.organization_id
                      AND image_generation_candidates.generation_id=EXCLUDED.generation_id
                """),
                {
                    "candidate_id": candidate.candidate_id,
                    "organization_id": job.organization_id,
                    "generation_id": job.generation_id,
                    "variant_index": candidate.variant_index,
                    "variant_operation_id": candidate.variant_operation_id,
                    "status": candidate.status.value,
                    "provider": candidate.provider,
                    "model": candidate.model,
                    "model_revision": candidate.model_revision,
                    "registry_snapshot_id": candidate.registry_snapshot_id,
                    "provider_request_id": candidate.provider_request_id,
                    "bucket": candidate.stored_image.bucket if candidate.stored_image else None,
                    "storage_key": (
                        candidate.stored_image.storage_key if candidate.stored_image else None
                    ),
                    "checksum": (
                        candidate.stored_image.checksum_sha256
                        if candidate.stored_image
                        else None
                    ),
                    "mime_type": (
                        candidate.stored_image.mime_type if candidate.stored_image else None
                    ),
                    "width": candidate.stored_image.width if candidate.stored_image else None,
                    "height": candidate.stored_image.height if candidate.stored_image else None,
                    "size_bytes": (
                        candidate.stored_image.size_bytes if candidate.stored_image else None
                    ),
                    "artifact_id": candidate.artifact_id,
                    "artifact_version_id": candidate.artifact_version_id,
                    "validation": (
                        _dump(candidate.validation)
                        if candidate.validation is not None
                        else "null"
                    ),
                    "provenance_snapshot_id": candidate.provenance_snapshot_id,
                    "cost_amount": candidate.cost_usd,
                    "cost_confidence": candidate.cost_confidence,
                    "pricing_snapshot_id": candidate.pricing_snapshot_id,
                    "routing": json.dumps(list(candidate.routing_reason_codes)),
                    "error_code": candidate.error_code,
                    "updated_at": job.updated_at,
                },
            )

