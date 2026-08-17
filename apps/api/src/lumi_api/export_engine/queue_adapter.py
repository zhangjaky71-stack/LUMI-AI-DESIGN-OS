from __future__ import annotations

from datetime import UTC, datetime
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy.orm import Session

from lumi_api.persistence.models_queue_runtime import RuntimeJobModel
from lumi_export_engine import ExportJob


class Node19ExportQueueAdapter:
    """Durable queue projection. Delivery/wakeup remains NODE-19 ownership."""

    def __init__(self, session: Session) -> None:
        self.session = session

    @staticmethod
    def runtime_id(export_job_id: str) -> UUID:
        return uuid5(NAMESPACE_URL, f"lumi:runtime:export.package:{export_job_id}")

    def enqueue(self, *, job: ExportJob) -> str:
        runtime_id = self.runtime_id(job.job_id)
        existing = self.session.get(RuntimeJobModel, runtime_id)
        if existing is not None:
            if (
                existing.organization_id != UUID(job.spec.organization_id)
                or existing.project_id != UUID(job.spec.project_id)
                or existing.job_kind != "export.package"
                or str(existing.resource_id) != job.job_id
            ):
                raise RuntimeError("EXPORT_RUNTIME_JOB_ID_CONFLICT")
            return str(runtime_id)
        self.session.add(
            RuntimeJobModel(
                id=runtime_id,
                organization_id=UUID(job.spec.organization_id),
                project_id=UUID(job.spec.project_id),
                job_kind="export.package",
                operation_id=UUID(job.spec.operation_id),
                resource_id=UUID(job.job_id),
                status="pending",
                attempt_count=0,
                max_attempts=3,
                input_json={
                    "export_job_id": job.job_id,
                    "semantic_hash": job.spec.semantic_hash(),
                    "artifact_version_ids": [
                        item.snapshot.artifact_version_id for item in job.items
                    ],
                },
                output_json={},
            )
        )
        self.session.commit()
        return str(runtime_id)

    def cancel(self, *, runtime_job_id: str) -> bool:
        row = self.session.get(RuntimeJobModel, UUID(runtime_job_id))
        if row is None:
            return False
        if row.status in {"succeeded", "failed", "cancelled"}:
            return False
        row.cancellation_requested_at = datetime.now(UTC)
        if row.status == "pending":
            row.status = "cancelled"
            row.finished_at = datetime.now(UTC)
            row.error_category = "cancelled"
            row.error_code = "EXPORT_CANCELLED_BEFORE_START"
        self.session.commit()
        return True
