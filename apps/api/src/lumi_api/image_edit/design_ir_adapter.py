from __future__ import annotations

from typing import Protocol
from uuid import NAMESPACE_URL, uuid5

from design_ir import apply_batch, apply_operation
from lumi_image_edit import ImageEditSpec, StructuralEditOperation


class DesignDocumentStore(Protocol):
    def load(self, document_id: str) -> dict: ...

    def save(
        self,
        document_id: str,
        document: dict,
        *,
        source_artifact_version_id: str | None,
    ) -> str: ...


class ConstraintPreflightPort(Protocol):
    def __call__(self, document: dict, operation: dict) -> list: ...


def _operation(value: StructuralEditOperation) -> dict:
    return {
        "operation_id": value.operation_id,
        "type": value.type,
        "target_ids": list(value.target_ids),
        "expected_document_version": value.expected_document_version,
        "payload": dict(value.payload),
        "reason": value.reason,
    }


class Node38StructuralEditAdapter:
    def __init__(
        self,
        store: DesignDocumentStore,
        preflight: ConstraintPreflightPort | None = None,
    ) -> None:
        self.store = store
        self.preflight = preflight

    async def apply(
        self,
        spec: ImageEditSpec,
        operations: tuple[StructuralEditOperation, ...],
    ) -> str:
        if not spec.design_document_id or spec.design_document_version is None:
            raise ValueError("IMAGE_EDIT_DESIGN_DOCUMENT_REQUIRED")
        document = self.store.load(spec.design_document_id)
        current = int(document.get("metadata", {}).get("document_version", 0))
        if current != spec.design_document_version:
            raise ValueError("IMAGE_EDIT_CANVAS_VERSION_CONFLICT")
        result = apply_batch(
            document,
            [_operation(operation) for operation in operations],
            spec.design_document_version,
            operation_id=f"image-edit:{spec.operation_id}:structural",
            preflight=self.preflight,
        )
        return self.store.save(
            spec.design_document_id,
            result.document,
            source_artifact_version_id=None,
        )


class Node38CanvasReplaceAssetAdapter:
    def __init__(
        self,
        store: DesignDocumentStore,
        preflight: ConstraintPreflightPort | None = None,
    ) -> None:
        self.store = store
        self.preflight = preflight

    async def replace_asset(
        self,
        *,
        spec: ImageEditSpec,
        asset_id: str,
    ) -> str:
        if (
            not spec.design_document_id
            or spec.design_document_version is None
            or not spec.intent.selected_node_ids
        ):
            raise ValueError("IMAGE_EDIT_CANVAS_TARGET_REQUIRED")
        document = self.store.load(spec.design_document_id)
        current = int(document.get("metadata", {}).get("document_version", 0))
        if current != spec.design_document_version:
            raise ValueError("IMAGE_EDIT_CANVAS_VERSION_CONFLICT")
        operation = {
            "operation_id": str(
                uuid5(
                    NAMESPACE_URL,
                    f"{spec.operation_id}:replace-asset",
                )
            ),
            "type": "REPLACE_ASSET",
            "target_ids": list(spec.intent.selected_node_ids),
            "expected_document_version": current,
            "payload": {"asset_id": asset_id},
            "reason": "NODE47_PASS_REPLACE_ASSET",
        }
        result = apply_operation(document, operation, self.preflight)
        return self.store.save(
            spec.design_document_id,
            result.document,
            source_artifact_version_id=spec.source.artifact_version_id,
        )
