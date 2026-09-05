from __future__ import annotations

from .model import EditJob, GatewayEditResult, ImageEditSpec


class ImageEditRepositoryError(ValueError):
    pass


class ImageEditOperationConflict(ImageEditRepositoryError):
    pass


class InMemoryImageEditRepository:
    def __init__(self) -> None:
        self.jobs: dict[tuple[str, str], EditJob] = {}
        self.operations: dict[tuple[str, str], str] = {}
        self.specs: dict[tuple[str, str], ImageEditSpec] = {}
        self.pending: dict[tuple[str, str], GatewayEditResult] = {}

    def get_by_operation(self, organization_id: str, operation_id: str) -> EditJob | None:
        edit_id = self.operations.get((organization_id, operation_id))
        return None if edit_id is None else self.jobs.get((organization_id, edit_id))

    def save(self, job: EditJob) -> None:
        op_key = (job.organization_id, job.operation_id)
        existing_id = self.operations.get(op_key)
        if existing_id is not None:
            existing = self.jobs[(job.organization_id, existing_id)]
            if existing.semantic_hash != job.semantic_hash:
                raise ImageEditOperationConflict("IMAGE_EDIT_OPERATION_SEMANTIC_CONFLICT")
            if existing.edit_id != job.edit_id:
                raise ImageEditRepositoryError("IMAGE_EDIT_OPERATION_REBOUND_FORBIDDEN")
        self.operations[op_key] = job.edit_id
        self.jobs[(job.organization_id, job.edit_id)] = job

    def save_spec(self, spec: ImageEditSpec) -> None:
        key = (spec.organization_id, spec.operation_id)
        existing = self.specs.get(key)
        if existing is not None and existing.semantic_hash != spec.semantic_hash:
            raise ImageEditOperationConflict("IMAGE_EDIT_OPERATION_SEMANTIC_CONFLICT")
        self.specs[key] = spec

    def get_spec(self, organization_id: str, operation_id: str) -> ImageEditSpec | None:
        return self.specs.get((organization_id, operation_id))

    def save_pending(self, organization_id: str, edit_id: str, result: GatewayEditResult) -> None:
        self.pending[(organization_id, edit_id)] = result

    def get_pending(self, organization_id: str, edit_id: str) -> GatewayEditResult | None:
        return self.pending.get((organization_id, edit_id))

    def delete_pending(self, organization_id: str, edit_id: str) -> None:
        self.pending.pop((organization_id, edit_id), None)
