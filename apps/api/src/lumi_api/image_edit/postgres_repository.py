from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from lumi_image_edit import EditJob, GatewayEditRequest, GatewayEditResult, ImageEditSpec
from lumi_image_edit.pipeline import edit_id as derive_edit_id
from lumi_image_edit.repository import OperationSemanticConflict
from lumi_api.persistence.models_image_edit import (
    ImageEditJobModel,
    ImageEditMaskModel,
    ImageEditPendingModel,
    ImageEditSpecModel,
)

from .postgres_codec import (
    decode_job,
    decode_request,
    decode_result,
    decode_spec,
    encode_job,
    encode_request,
    encode_result,
    encode_spec,
)


class PostgresImageEditRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def bind_spec(self, edit_id: str, spec: ImageEditSpec) -> None:
        edit_uuid = UUID(edit_id)
        organization_id = UUID(spec.organization_id)
        operation_id = UUID(spec.operation_id)
        prior = self.session.scalar(
            select(ImageEditSpecModel).where(
                ImageEditSpecModel.organization_id == organization_id,
                ImageEditSpecModel.operation_id == operation_id,
            )
        )
        if prior and prior.edit_id != edit_uuid:
            raise OperationSemanticConflict("IMAGE_EDIT_OPERATION_ALREADY_BOUND")
        if prior and prior.semantic_hash != spec.semantic_hash:
            raise OperationSemanticConflict("IMAGE_EDIT_OPERATION_SEMANTIC_CONFLICT")

        row = self.session.get(ImageEditSpecModel, edit_uuid)
        if row is None:
            row = ImageEditSpecModel(
                edit_id=edit_uuid,
                organization_id=organization_id,
                project_id=UUID(spec.project_id),
                task_id=UUID(spec.task_id),
                operation_id=operation_id,
                semantic_hash=spec.semantic_hash,
                source_artifact_version_id=UUID(
                    spec.source.artifact_version_id
                ),
                source_asset_id=UUID(spec.source.asset_id),
                source_asset_version=spec.source.asset_version,
                source_checksum_sha256=spec.source.checksum_sha256,
                spec_json=encode_spec(spec),
            )
            self.session.add(row)
        else:
            if row.semantic_hash != spec.semantic_hash:
                raise OperationSemanticConflict("IMAGE_EDIT_SPEC_SEMANTIC_CONFLICT")
            row.spec_json = encode_spec(spec)
        self._sync_mask(edit_uuid, organization_id, spec)
        self.session.commit()

    def save_spec(self, spec: ImageEditSpec) -> None:
        self.bind_spec(derive_edit_id(spec), spec)

    def _sync_mask(
        self,
        edit_id: UUID,
        organization_id: UUID,
        spec: ImageEditSpec,
    ) -> None:
        row = self.session.get(ImageEditMaskModel, edit_id)
        if spec.mask is None:
            if row:
                self.session.delete(row)
            return
        mask = spec.mask
        rect = {
            "x": mask.editable_rect.x,
            "y": mask.editable_rect.y,
            "width": mask.editable_rect.width,
            "height": mask.editable_rect.height,
        }
        values = {
            "organization_id": organization_id,
            "mask_id": UUID(mask.mask_id),
            "version": mask.version,
            "source": mask.source,
            "checksum_sha256": mask.checksum_sha256,
            "source_checksum_sha256": mask.source_checksum_sha256,
            "source_width": mask.source_width,
            "source_height": mask.source_height,
            "editable_rect_json": rect,
            "durable_ref": mask.durable_ref,
            "preview_required": mask.preview_required,
            "preview_approved_by": mask.preview_approved_by,
        }
        if row is None:
            self.session.add(ImageEditMaskModel(edit_id=edit_id, **values))
        else:
            for key, value in values.items():
                setattr(row, key, value)

    def get_spec(self, org: str, edit_id: str) -> ImageEditSpec:
        row = self.session.get(ImageEditSpecModel, UUID(edit_id))
        if row is None or row.organization_id != UUID(org):
            raise LookupError("IMAGE_EDIT_SPEC_NOT_FOUND")
        return decode_spec(dict(row.spec_json))

    def save(self, job: EditJob) -> None:
        edit_uuid = UUID(job.edit_id)
        spec = self.session.get(ImageEditSpecModel, edit_uuid)
        if spec is None:
            raise LookupError("IMAGE_EDIT_SPEC_REQUIRED_BEFORE_JOB")
        if (
            spec.organization_id != UUID(job.organization_id)
            or spec.semantic_hash != job.semantic_hash
        ):
            raise OperationSemanticConflict("IMAGE_EDIT_JOB_SPEC_CONFLICT")
        row = self.session.get(ImageEditJobModel, edit_uuid)
        values = {
            "organization_id": UUID(job.organization_id),
            "route": job.route,
            "status": job.status,
            "result_artifact_version_id": (
                UUID(job.result_artifact_version_id)
                if job.result_artifact_version_id
                else None
            ),
            "result_design_document_version_id": (
                job.result_design_document_version_id
            ),
            "result_asset_id": (
                UUID(job.result_asset_id) if job.result_asset_id else None
            ),
            "provider": job.provider,
            "model": job.model,
            "provider_request_id": job.provider_request_id,
            "provenance_snapshot_id": job.provenance_snapshot_id,
            "validation_decision": job.validation_decision,
            "error_code": job.error_code,
            "job_json": encode_job(job),
            "updated_at": datetime.now(UTC),
        }
        if row is None:
            self.session.add(ImageEditJobModel(edit_id=edit_uuid, **values))
        else:
            for key, value in values.items():
                setattr(row, key, value)
        self.session.commit()

    def get(self, org: str, edit_id: str) -> EditJob | None:
        row = self.session.get(ImageEditJobModel, UUID(edit_id))
        if row is None or row.organization_id != UUID(org):
            return None
        return decode_job(dict(row.job_json))

    def get_by_operation(self, org: str, operation_id: str) -> EditJob | None:
        spec = self.session.scalar(
            select(ImageEditSpecModel).where(
                ImageEditSpecModel.organization_id == UUID(org),
                ImageEditSpecModel.operation_id == UUID(operation_id),
            )
        )
        if spec is None:
            return None
        row = self.session.get(ImageEditJobModel, spec.edit_id)
        return decode_job(dict(row.job_json)) if row else None

    def save_pending(
        self,
        edit_id: str,
        request: GatewayEditRequest,
        result: GatewayEditResult,
    ) -> None:
        if result.status != "PENDING" or not result.provider_request_id:
            raise ValueError("IMAGE_EDIT_PENDING_RESULT_REQUIRED")
        edit_uuid = UUID(edit_id)
        row = self.session.get(ImageEditPendingModel, edit_uuid)
        values = {
            "organization_id": UUID(request.organization_id),
            "provider": result.provider,
            "model": result.model,
            "provider_request_id": result.provider_request_id,
            "request_json": encode_request(request),
            "result_json": encode_result(result),
        }
        if row is None:
            self.session.add(ImageEditPendingModel(edit_id=edit_uuid, **values))
        else:
            for key, value in values.items():
                setattr(row, key, value)
            row.poll_attempts += 1
            row.last_polled_at = datetime.now(UTC)
        self.session.commit()

    def get_pending(
        self,
        edit_id: str,
    ) -> tuple[GatewayEditRequest, GatewayEditResult] | None:
        row = self.session.get(ImageEditPendingModel, UUID(edit_id))
        if row is None:
            return None
        return (
            decode_request(dict(row.request_json)),
            decode_result(dict(row.result_json)),
        )

    def delete_pending(self, edit_id: str) -> None:
        row = self.session.get(ImageEditPendingModel, UUID(edit_id))
        if row:
            self.session.delete(row)
            self.session.commit()
