from __future__ import annotations

from threading import RLock

from .model import EditJob, GatewayEditRequest, GatewayEditResult, ImageEditSpec


class OperationSemanticConflict(RuntimeError):
    pass


class InMemoryEditRepository:
    def __init__(self) -> None:
        self._lock = RLock()
        self.jobs: dict[str, EditJob] = {}
        self.operations: dict[tuple[str, str], EditJob] = {}
        self.specs: dict[tuple[str, str], ImageEditSpec] = {}
        self.pending: dict[
            str,
            tuple[GatewayEditRequest, GatewayEditResult],
        ] = {}

    def get_by_operation(self, org: str, operation_id: str) -> EditJob | None:
        return self.operations.get((org, operation_id))

    def get(self, org: str, edit_id: str) -> EditJob | None:
        job = self.jobs.get(edit_id)
        return job if job and job.organization_id == org else None

    def save_spec(self, spec: ImageEditSpec) -> None:
        self.specs[spec.organization_id, self._edit_id(spec)] = spec

    def bind_spec(self, edit_id: str, spec: ImageEditSpec) -> None:
        self.specs[spec.organization_id, edit_id] = spec

    def get_spec(self, org: str, edit_id: str) -> ImageEditSpec:
        try:
            return self.specs[org, edit_id]
        except KeyError as exc:
            raise LookupError("IMAGE_EDIT_SPEC_NOT_FOUND") from exc

    def save(self, job: EditJob) -> None:
        with self._lock:
            prior = self.operations.get((job.organization_id, job.operation_id))
            if prior and prior.edit_id != job.edit_id:
                raise OperationSemanticConflict("IMAGE_EDIT_OPERATION_ALREADY_BOUND")
            if prior and prior.semantic_hash != job.semantic_hash:
                raise OperationSemanticConflict("IMAGE_EDIT_OPERATION_SEMANTIC_CONFLICT")
            self.jobs[job.edit_id] = job
            self.operations[job.organization_id, job.operation_id] = job

    def save_pending(
        self,
        edit_id: str,
        request: GatewayEditRequest,
        result: GatewayEditResult,
    ) -> None:
        self.pending[edit_id] = (request, result)

    def get_pending(
        self,
        edit_id: str,
    ) -> tuple[GatewayEditRequest, GatewayEditResult] | None:
        return self.pending.get(edit_id)

    def delete_pending(self, edit_id: str) -> None:
        self.pending.pop(edit_id, None)

    @staticmethod
    def _edit_id(spec: ImageEditSpec) -> str:
        return "edit:" + spec.semantic_hash[:24]
