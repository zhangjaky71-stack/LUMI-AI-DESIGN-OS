from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Any, Iterator
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from lumi_image_generation import GenerationJob, ImageGenerationSpec, PendingInvocation
from lumi_image_generation.ports import CostProjection
from lumi_image_generation.repository import OperationSemanticConflict

from .postgres_codec import _dump, _gateway_request, _gateway_result, _job, _spec


class PostgresGenerationRepository:
    """Dedicated-session repository. NODE-46 state is tenant-scoped and operation-idempotent."""

    def __init__(self, session: Session) -> None:
        self.session = session

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        if self.session.in_transaction():
            self.session.rollback()
        with self.session.begin():
            yield

    @staticmethod
    def _payload(row, key: str) -> dict[str, Any]:
        value = row[key]
        return json.loads(value) if isinstance(value, str) else dict(value)

    def get_by_operation(
        self, organization_id: UUID, operation_id: UUID
    ) -> GenerationJob | None:
        row = self.session.execute(
            text("""
                SELECT job_json FROM image_generation_jobs
                WHERE organization_id=:organization_id AND operation_id=:operation_id
            """),
            {"organization_id": organization_id, "operation_id": operation_id},
        ).mappings().first()
        return None if row is None else _job(self._payload(row, "job_json"))

    def save_spec(self, spec: ImageGenerationSpec) -> None:
        payload = _dump(spec)
        with self._transaction():
            result = self.session.execute(
                text("""
                    INSERT INTO image_generation_specs(
                        organization_id, operation_id, project_id, task_id,
                        semantic_hash, spec_json
                    ) VALUES (
                        :organization_id, :operation_id, :project_id, :task_id,
                        :semantic_hash, CAST(:spec_json AS jsonb)
                    )
                    ON CONFLICT (organization_id, operation_id) DO NOTHING
                """),
                {
                    "organization_id": spec.organization_id,
                    "operation_id": spec.operation_id,
                    "project_id": spec.project_id,
                    "task_id": spec.task_id,
                    "semantic_hash": spec.semantic_hash,
                    "spec_json": payload,
                },
            )
            if result.rowcount == 0:
                existing = self.session.execute(
                    text("""
                        SELECT semantic_hash FROM image_generation_specs
                        WHERE organization_id=:organization_id AND operation_id=:operation_id
                    """),
                    {
                        "organization_id": spec.organization_id,
                        "operation_id": spec.operation_id,
                    },
                ).scalar_one()
                if existing != spec.semantic_hash:
                    raise OperationSemanticConflict("GENERATION_OPERATION_SEMANTIC_CONFLICT")

    def get_spec(
        self, organization_id: UUID, operation_id: UUID
    ) -> ImageGenerationSpec | None:
        row = self.session.execute(
            text("""
                SELECT spec_json FROM image_generation_specs
                WHERE organization_id=:organization_id AND operation_id=:operation_id
            """),
            {"organization_id": organization_id, "operation_id": operation_id},
        ).mappings().first()
        return None if row is None else _spec(self._payload(row, "spec_json"))

    def save(self, job: GenerationJob) -> None:
        from .postgres_job_write import save_job

        save_job(self, job)

    def get(self, organization_id: UUID, generation_id: UUID) -> GenerationJob | None:
        row = self.session.execute(
            text("""
                SELECT job_json FROM image_generation_jobs
                WHERE organization_id=:organization_id AND generation_id=:generation_id
            """),
            {"organization_id": organization_id, "generation_id": generation_id},
        ).mappings().first()
        return None if row is None else _job(self._payload(row, "job_json"))

    def save_pending(self, value: PendingInvocation) -> None:
        with self._transaction():
            self.session.execute(
                text("""
                    INSERT INTO image_generation_pending(
                        candidate_id, organization_id, generation_id, provider, model,
                        provider_request_id, request_json, result_json, queued_at,
                        last_polled_at, poll_attempts
                    ) VALUES (
                        :candidate_id, :organization_id, :generation_id, :provider, :model,
                        :provider_request_id, CAST(:request_json AS jsonb),
                        CAST(:result_json AS jsonb),
                        CAST(:queued_at AS timestamptz), CAST(:last_polled_at AS timestamptz),
                        :poll_attempts
                    )
                    ON CONFLICT (candidate_id) DO UPDATE SET
                        result_json=EXCLUDED.result_json,
                        last_polled_at=EXCLUDED.last_polled_at,
                        poll_attempts=EXCLUDED.poll_attempts
                    WHERE image_generation_pending.organization_id=EXCLUDED.organization_id
                """),
                {
                    "candidate_id": value.candidate_id,
                    "organization_id": value.organization_id,
                    "generation_id": value.generation_id,
                    "provider": value.result.provider,
                    "model": value.result.model,
                    "provider_request_id": value.result.provider_request_id,
                    "request_json": _dump(value.request),
                    "result_json": _dump(value.result),
                    "queued_at": value.queued_at,
                    "last_polled_at": value.last_polled_at,
                    "poll_attempts": value.poll_attempts,
                },
            )

    def get_pending(
        self, organization_id: UUID, generation_id: UUID, candidate_id: UUID
    ) -> PendingInvocation | None:
        row = self.session.execute(
            text("""
                SELECT request_json, result_json, queued_at, last_polled_at, poll_attempts
                FROM image_generation_pending
                WHERE organization_id=:organization_id
                  AND generation_id=:generation_id AND candidate_id=:candidate_id
            """),
            {
                "organization_id": organization_id,
                "generation_id": generation_id,
                "candidate_id": candidate_id,
            },
        ).mappings().first()
        if row is None:
            return None
        request_json = self._payload(row, "request_json")
        result_json = self._payload(row, "result_json")
        return PendingInvocation(
            organization_id=organization_id,
            generation_id=generation_id,
            candidate_id=candidate_id,
            request=_gateway_request(request_json),
            result=_gateway_result(result_json),
            queued_at=row["queued_at"].isoformat(),
            last_polled_at=(
                row["last_polled_at"].isoformat() if row["last_polled_at"] else None
            ),
            poll_attempts=int(row["poll_attempts"]),
        )

    def delete_pending(
        self, organization_id: UUID, generation_id: UUID, candidate_id: UUID
    ) -> None:
        with self._transaction():
            self.session.execute(
                text("""
                    DELETE FROM image_generation_pending
                    WHERE organization_id=:organization_id
                      AND generation_id=:generation_id AND candidate_id=:candidate_id
                """),
                {
                    "organization_id": organization_id,
                    "generation_id": generation_id,
                    "candidate_id": candidate_id,
                },
            )


class PostgresGenerationCostProjection:
    """Audit projection only. NODE-27 settlement through NODE-22 remains monetary truth."""

    def __init__(self, session: Session) -> None:
        self.session = session

    async def record(self, projection: CostProjection) -> None:
        if self.session.in_transaction():
            self.session.rollback()
        with self.session.begin():
            self.session.execute(
                text("""
                    INSERT INTO image_generation_cost_projection(
                        candidate_id, generation_id, operation_id, provider, model,
                        provider_request_id, amount, confidence, pricing_snapshot_id,
                        monetary_owner
                    ) VALUES (
                        :candidate_id, :generation_id, :operation_id, :provider, :model,
                        :provider_request_id, :amount, :confidence, :pricing_snapshot_id,
                        'NODE27_MODEL_GATEWAY_SETTLEMENT'
                    )
                    ON CONFLICT (candidate_id) DO UPDATE SET
                        provider_request_id=EXCLUDED.provider_request_id,
                        amount=EXCLUDED.amount,
                        confidence=EXCLUDED.confidence,
                        pricing_snapshot_id=EXCLUDED.pricing_snapshot_id
                """),
                {
                    "candidate_id": projection.candidate_id,
                    "generation_id": projection.generation_id,
                    "operation_id": projection.operation_id,
                    "provider": projection.provider,
                    "model": projection.model,
                    "provider_request_id": projection.provider_request_id,
                    "amount": projection.amount_usd,
                    "confidence": projection.confidence,
                    "pricing_snapshot_id": projection.pricing_snapshot_id,
                },
            )
