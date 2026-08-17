from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from lumi_api.persistence.models_export_engine import (
    ExportDownloadGrantModel,
    ExportItemModel,
    ExportJobModel,
    ExportOutputModel,
    ExportSpecModel,
)
from lumi_export_engine import DownloadGrant, ExportJob
from lumi_export_engine.pipeline import ExportOperationConflict

from .codec import encode_job, encode_output, encode_package, encode_snapshot


class PostgresExportRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, job: ExportJob) -> ExportJob:
        organization_id = UUID(job.spec.organization_id)
        operation_id = UUID(job.spec.operation_id)
        prior = self.session.scalar(
            select(ExportSpecModel).where(
                ExportSpecModel.organization_id == organization_id,
                ExportSpecModel.operation_id == operation_id,
            )
        )
        if prior is not None:
            if prior.semantic_hash != job.spec.semantic_hash():
                raise ExportOperationConflict(
                    "EXPORT_OPERATION_ID_REUSED_WITH_DIFFERENT_SPEC"
                )
            return self.get(str(prior.export_job_id))
        job_id = UUID(job.job_id)
        encoded = encode_job(job)
        self.session.add(
            ExportSpecModel(
                export_job_id=job_id,
                organization_id=organization_id,
                project_id=UUID(job.spec.project_id),
                task_id=UUID(job.spec.task_id),
                operation_id=operation_id,
                requested_by=job.spec.requested_by,
                semantic_hash=job.spec.semantic_hash(),
                spec_json=encoded["spec"],
            )
        )
        self.session.flush()
        self._write(job, encoded)
        self.session.commit()
        return job

    def get(self, job_id: str) -> ExportJob:
        row = self.session.get(ExportJobModel, UUID(job_id))
        if row is None:
            raise KeyError("EXPORT_JOB_NOT_FOUND")
        from .codec import decode_job

        return decode_job(dict(row.job_json))

    def save(self, job: ExportJob) -> ExportJob:
        spec = self.session.get(ExportSpecModel, UUID(job.job_id))
        if spec is None:
            raise KeyError("EXPORT_JOB_NOT_FOUND")
        if (
            spec.organization_id != UUID(job.spec.organization_id)
            or spec.semantic_hash != job.spec.semantic_hash()
        ):
            raise ExportOperationConflict("EXPORT_JOB_SPEC_CONFLICT")
        encoded = encode_job(job)
        self._write(job, encoded)
        self.session.commit()
        return job

    def _write(self, job: ExportJob, encoded: dict[str, Any]) -> None:
        job_id = UUID(job.job_id)
        row = self.session.get(ExportJobModel, job_id)
        package_json = None if job.package is None else encode_package(job.package)
        values: dict[str, Any] = {
            "organization_id": UUID(job.spec.organization_id),
            "status": job.status.value,
            "runtime_job_id": UUID(job.runtime_job_id) if job.runtime_job_id else None,
            "package_id": UUID(job.package.package_id) if job.package else None,
            "package_json": package_json,
            "manifest_json": (
                None if package_json is None else package_json["manifest"]
            ),
            "job_json": encoded,
            "error_code": job.error_code,
            "updated_at": datetime.now(UTC),
        }
        if row is None:
            self.session.add(ExportJobModel(export_job_id=job_id, **values))
        else:
            for key, value in values.items():
                setattr(row, key, value)
        self._sync_items(job)
        self._sync_outputs(job)

    def _sync_items(self, job: ExportJob) -> None:
        job_id = UUID(job.job_id)
        for ordinal, runtime in enumerate(job.items):
            row = self.session.get(ExportItemModel, (job_id, ordinal))
            snapshot = encode_snapshot(runtime.snapshot)
            snapshot_hash = hashlib.sha256(
                json.dumps(snapshot, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            values: dict[str, Any] = {
                "organization_id": UUID(job.spec.organization_id),
                "artifact_id": UUID(runtime.snapshot.artifact_id),
                "artifact_version_id": UUID(runtime.snapshot.artifact_version_id),
                "target_format": runtime.request.target_format.value,
                "output_name": runtime.request.output_name,
                "snapshot_hash": snapshot_hash,
                "snapshot_json": snapshot,
            }
            if row is None:
                self.session.add(
                    ExportItemModel(
                        export_job_id=job_id,
                        ordinal=ordinal,
                        **values,
                    )
                )
            else:
                for key, value in values.items():
                    setattr(row, key, value)

    def _sync_outputs(self, job: ExportJob) -> None:
        job_id = UUID(job.job_id)
        self.session.execute(
            delete(ExportOutputModel).where(
                ExportOutputModel.export_job_id == job_id
            )
        )
        for ordinal, output in enumerate(job.outputs):
            self.session.add(
                ExportOutputModel(
                    export_job_id=job_id,
                    ordinal=ordinal,
                    organization_id=UUID(job.spec.organization_id),
                    source_artifact_id=UUID(output.source_artifact_id),
                    source_artifact_version_id=UUID(
                        output.source_artifact_version_id
                    ),
                    filename=output.name,
                    mime_type=output.mime_type,
                    bucket=output.bucket,
                    storage_key=output.storage_key,
                    size_bytes=output.size_bytes,
                    checksum_sha256=output.checksum_sha256,
                    renderer_version=output.renderer_version,
                    output_json=encode_output(output),
                )
            )

    def record_grant(self, grant: DownloadGrant) -> None:
        if self.session.get(ExportDownloadGrantModel, UUID(grant.grant_id)) is not None:
            return
        job = self.get_by_package(grant.package_id)
        self.session.add(
            ExportDownloadGrantModel(
                grant_id=UUID(grant.grant_id),
                export_job_id=UUID(job.job_id),
                organization_id=UUID(job.spec.organization_id),
                package_id=UUID(grant.package_id),
                actor_id=grant.actor_id,
                expires_at=grant.expires_at,
            )
        )
        self.session.commit()

    def get_by_package(self, package_id: str) -> ExportJob:
        row = self.session.scalar(
            select(ExportJobModel).where(
                ExportJobModel.package_id == UUID(package_id)
            )
        )
        if row is None:
            raise KeyError("EXPORT_PACKAGE_NOT_FOUND")
        from .codec import decode_job

        return decode_job(dict(row.job_json))
