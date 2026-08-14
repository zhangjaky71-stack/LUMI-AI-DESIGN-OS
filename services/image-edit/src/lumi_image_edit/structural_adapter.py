from __future__ import annotations

from typing import Protocol

from .model import ImageEditSpec, StructuralEditOperation
from .ports import StructuralEditResult


class DesignOperationExecutor(Protocol):
    async def execute(
        self,
        *,
        organization_id: str,
        project_id: str,
        document_id: str,
        operations: tuple[dict[str, object], ...],
    ) -> StructuralEditResult: ...


class DesignIrStructuralAdapter:
    """Transport-neutral bridge to NODE-38 + NODE-39 guarded DesignOperation execution."""

    def __init__(self, executor: DesignOperationExecutor) -> None:
        self.executor = executor

    async def apply(
        self,
        *,
        spec: ImageEditSpec,
        operations: tuple[StructuralEditOperation, ...],
    ) -> StructuralEditResult:
        if spec.design_document_id is None:
            raise ValueError("IMAGE_EDIT_STRUCTURAL_DOCUMENT_REQUIRED")
        payloads = tuple(
            {
                "operation_id": operation.operation_id,
                "type": operation.type,
                "target_ids": list(operation.target_ids),
                "expected_document_version": operation.expected_document_version,
                "payload": dict(operation.payload),
                "reason": operation.reason,
            }
            for operation in operations
        )
        return await self.executor.execute(
            organization_id=spec.organization_id,
            project_id=spec.project_id,
            document_id=spec.design_document_id,
            operations=payloads,
        )
