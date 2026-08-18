from __future__ import annotations

import json
import math
from collections.abc import Iterable
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from lumi_api.design_ir.document import (
    DesignIRDocument,
    content_hash_sha256,
    node_index,
)
from lumi_api.design_ir.engine import OperationRejected, RevisionConflict, apply_batch
from lumi_api.design_ir.nodes import FrameNode, GroupNode, ImageNode, PageNode, TextNode
from lumi_api.design_ir.operations import (
    ActorRef,
    AddNodeOp,
    DesignOperation,
    DesignOperationBatch,
    RemoveNodeOp,
    RenameNodeOp,
    SetAppearanceOp,
    SetImageAssetOp,
    SetLockOp,
    SetSizeOp,
    SetTextOp,
    SetTransformOp,
)
from lumi_api.design_ir.primitives import Size2D, Transform2D
from lumi_api.domain.ids import new_uuid7

from .canvas_document_schemas import (
    CanvasCommandBatchRequest,
    CanvasCommandBatchResponse,
    CanvasDocumentProjectionResponse,
    CanvasOperationDescriptorRequest,
)
from .errors import ApiProblem


class PostgresCanvasDocumentService:
    """Tenant-scoped projection + atomic DesignDocument command application.

    The browser canvas is a renderer/editor projection only. Every persisted write
    locks the DesignDocument head, fences the exact expected head/version/revision,
    compiles browser descriptors into the Python Design IR runtime, writes one
    immutable DesignDocumentVersion, and advances the canonical head in the same
    transaction.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    async def get_document_head(
        self,
        *,
        organization_id: UUID,
        design_document_id: UUID,
    ) -> CanvasDocumentProjectionResponse:
        row = self.session.execute(
            text(
                """
                SELECT d.id AS design_document_id, d.head_version_id,
                       v.id AS version_id, v.version_number,
                       v.content_json, v.content_hash
                FROM design_documents d
                JOIN design_document_versions v
                  ON v.id=d.head_version_id
                 AND v.organization_id=d.organization_id
                WHERE d.id=:document_id
                  AND d.organization_id=:organization_id
                  AND d.deleted_at IS NULL
                """
            ),
            {"document_id": design_document_id, "organization_id": organization_id},
        ).mappings().one_or_none()
        if row is None:
            raise _not_found()
        return _projection(row)

    async def get_artifact_version_document(
        self,
        *,
        organization_id: UUID,
        artifact_version_id: UUID,
    ) -> CanvasDocumentProjectionResponse:
        row = self.session.execute(
            text(
                """
                SELECT d.id AS design_document_id, d.head_version_id,
                       v.id AS version_id, v.version_number,
                       v.content_json, v.content_hash
                FROM artifact_versions av
                JOIN artifacts a
                  ON a.id=av.artifact_id
                 AND a.organization_id=av.organization_id
                JOIN design_document_versions v
                  ON v.id=av.design_document_version_id
                 AND v.organization_id=av.organization_id
                JOIN design_documents d
                  ON d.id=v.design_document_id
                 AND d.organization_id=v.organization_id
                WHERE av.id=:artifact_version_id
                  AND av.organization_id=:organization_id
                  AND a.deleted_at IS NULL
                  AND d.deleted_at IS NULL
                """
            ),
            {
                "artifact_version_id": artifact_version_id,
                "organization_id": organization_id,
            },
        ).mappings().one_or_none()
        if row is None:
            raise ApiProblem(
                status=404,
                code="canvas_artifact_version_not_editable",
                title="Canvas document unavailable",
                detail=(
                    "The exact artifact version does not expose an authorized "
                    "DesignDocumentVersion for this organization."
                ),
            )
        return _projection(row)

    async def apply_commands(
        self,
        *,
        organization_id: UUID,
        design_document_id: UUID,
        request: CanvasCommandBatchRequest,
        actor_id: str,
    ) -> CanvasCommandBatchResponse:
        if self.session.in_transaction():
            self.session.rollback()
        with self.session.begin():
            document_row = self.session.execute(
                text(
                    """
                    SELECT id, head_version_id
                    FROM design_documents
                    WHERE id=:document_id
                      AND organization_id=:organization_id
                      AND deleted_at IS NULL
                    FOR UPDATE
                    """
                ),
                {
                    "document_id": design_document_id,
                    "organization_id": organization_id,
                },
            ).mappings().one_or_none()
            if document_row is None:
                raise _not_found()
            head_id = document_row["head_version_id"]
            if head_id != request.expected_design_document_version_id:
                replay = self._replayed_batch(
                    organization_id=organization_id,
                    design_document_id=design_document_id,
                    head_version_id=head_id,
                    request=request,
                )
                if replay is not None:
                    return replay
                raise _conflict("CANVAS_HEAD_VERSION_CONFLICT")

            version_row = self._version_row(
                organization_id=organization_id,
                design_document_id=design_document_id,
                version_id=head_id,
            )
            if version_row is None:
                raise _conflict("CANVAS_HEAD_VERSION_MISSING")
            if int(version_row["version_number"]) != request.expected_version_number:
                raise _conflict("CANVAS_VERSION_NUMBER_CONFLICT")

            document = DesignIRDocument.model_validate(version_row["content_json"])
            if document.document_id != design_document_id:
                raise ApiProblem(
                    status=503,
                    code="canvas_document_identity_corrupt",
                    title="Canvas document invalid",
                    detail="Stored Design IR document identity does not match its owner row.",
                )
            if document.revision != request.expected_revision:
                raise _conflict("CANVAS_REVISION_CONFLICT")

            operations = tuple(_compile_descriptors(document, request.descriptors))
            batch = DesignOperationBatch(
                operation_id=new_uuid7(),
                document_id=document.document_id,
                base_revision=document.revision,
                actor=ActorRef(kind="user", actor_id=actor_id),
                correlation_id=str(request.client_batch_id),
                operations=operations,
            )
            try:
                result = apply_batch(document, batch)
            except RevisionConflict as exc:
                raise _conflict("CANVAS_REVISION_CONFLICT") from exc
            except OperationRejected as exc:
                raise ApiProblem(
                    status=422,
                    code="canvas_operation_rejected",
                    title="Canvas edit rejected",
                    detail=str(exc),
                ) from exc

            updated_document = result.document.model_copy(
                update={
                    "metadata": {
                        **result.document.metadata,
                        "canvas_last_client_batch_id": str(request.client_batch_id),
                    }
                }
            )
            content_hash = content_hash_sha256(updated_document)
            next_number = int(
                self.session.execute(
                    text(
                        """
                        SELECT COALESCE(MAX(version_number), 0) + 1
                        FROM design_document_versions
                        WHERE design_document_id=:document_id
                          AND organization_id=:organization_id
                        """
                    ),
                    {
                        "document_id": design_document_id,
                        "organization_id": organization_id,
                    },
                ).scalar_one()
            )
            next_version_id = new_uuid7()
            self.session.execute(
                text(
                    """
                    INSERT INTO design_document_versions(
                        id, organization_id, design_document_id, version_number,
                        parent_version_id, content_json, content_hash, created_by,
                        created_at
                    ) VALUES (
                        :id, :organization_id, :document_id, :version_number,
                        :parent_version_id, CAST(:content_json AS jsonb), :content_hash,
                        NULL, now()
                    )
                    """
                ),
                {
                    "id": next_version_id,
                    "organization_id": organization_id,
                    "document_id": design_document_id,
                    "version_number": next_number,
                    "parent_version_id": head_id,
                    "content_json": json.dumps(
                        updated_document.model_dump(mode="json"),
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    "content_hash": content_hash,
                },
            )
            updated = self.session.execute(
                text(
                    """
                    UPDATE design_documents
                    SET head_version_id=:next_version_id,
                        updated_at=now(), version=version+1
                    WHERE id=:document_id
                      AND organization_id=:organization_id
                      AND head_version_id=:expected_head
                    """
                ),
                {
                    "next_version_id": next_version_id,
                    "document_id": design_document_id,
                    "organization_id": organization_id,
                    "expected_head": head_id,
                },
            )
            if updated.rowcount != 1:
                raise _conflict("CANVAS_HEAD_VERSION_CONFLICT")

            projection = project_design_document(
                document=updated_document,
                version_id=next_version_id,
                version_number=next_number,
                content_hash=content_hash,
            )
            return CanvasCommandBatchResponse(
                client_batch_id=request.client_batch_id,
                projection=projection,
                applied_descriptors=len(request.descriptors),
            )

    def _version_row(
        self,
        *,
        organization_id: UUID,
        design_document_id: UUID,
        version_id: UUID | None,
    ) -> Any | None:
        if version_id is None:
            return None
        return self.session.execute(
            text(
                """
                SELECT id AS version_id, design_document_id, version_number,
                       content_json, content_hash
                FROM design_document_versions
                WHERE id=:version_id
                  AND design_document_id=:document_id
                  AND organization_id=:organization_id
                """
            ),
            {
                "version_id": version_id,
                "document_id": design_document_id,
                "organization_id": organization_id,
            },
        ).mappings().one_or_none()

    def _replayed_batch(
        self,
        *,
        organization_id: UUID,
        design_document_id: UUID,
        head_version_id: UUID | None,
        request: CanvasCommandBatchRequest,
    ) -> CanvasCommandBatchResponse | None:
        row = self._version_row(
            organization_id=organization_id,
            design_document_id=design_document_id,
            version_id=head_version_id,
        )
        if row is None:
            return None
        document = DesignIRDocument.model_validate(row["content_json"])
        if document.metadata.get("canvas_last_client_batch_id") != str(request.client_batch_id):
            return None
        return CanvasCommandBatchResponse(
            client_batch_id=request.client_batch_id,
            projection=project_design_document(
                document=document,
                version_id=row["version_id"],
                version_number=int(row["version_number"]),
                content_hash=str(row["content_hash"]),
            ),
            applied_descriptors=len(request.descriptors),
        )


def project_design_document(
    *,
    document: DesignIRDocument,
    version_id: UUID,
    version_number: int,
    content_hash: str,
) -> CanvasDocumentProjectionResponse:
    root_id = f"document-root:{document.document_id}"
    projected: dict[str, Any] = {
        root_id: {
            "id": root_id,
            "kind": "DOCUMENT_ROOT",
            "name": "Document",
            "parent_id": None,
            "children": [str(page_id) for page_id in document.pages],
            "visible": False,
            "locked": True,
            "opacity": 1,
            "transform": {"x": 0, "y": 0, "width": 0, "height": 0},
        }
    }
    for node in document.nodes:
        projected[str(node.id)] = _project_node(node)
    active_page = document.pages[0]
    return CanvasDocumentProjectionResponse(
        design_document_id=document.document_id,
        design_document_version_id=version_id,
        version_number=version_number,
        revision=document.revision,
        content_hash=content_hash,
        active_page_id=active_page,
        document={
            "schema_version": "lumi.design-ir/1.0",
            "document_id": str(document.document_id),
            "unit": "px",
            "root_id": root_id,
            "nodes": projected,
            "resources": {},
            "metadata": {
                "document_version": document.revision,
                "design_document_version_id": str(version_id),
                "version_number": version_number,
                "content_hash": content_hash,
                "active_page_id": str(active_page),
                "projection_schema": "lumi.canvas-projection/1.0",
            },
        },
    )


def _projection(row: Any) -> CanvasDocumentProjectionResponse:
    document = DesignIRDocument.model_validate(row["content_json"])
    return project_design_document(
        document=document,
        version_id=row["version_id"],
        version_number=int(row["version_number"]),
        content_hash=str(row["content_hash"]),
    )


def _project_node(node: Any) -> dict[str, Any]:
    kind = {
        "page": "GROUP",
        "frame": "FRAME",
        "group": "GROUP",
        "text": "TEXT",
        "image": "IMAGE",
        "shape": "SHAPE",
        "vector": "VECTOR_PATH",
    }[node.kind]
    transform = node.transform.model_dump(mode="json")
    size = getattr(node, "size", None)
    if size is not None:
        transform = {**transform, "width": float(size.width), "height": float(size.height)}
    children = getattr(node, "children", ())
    result: dict[str, Any] = {
        "id": str(node.id),
        "kind": kind,
        "name": node.name,
        "parent_id": str(node.parent_id) if node.parent_id else None,
        "children": [str(item) for item in children],
        "visible": False if isinstance(node, PageNode) else node.visible,
        "locked": True if isinstance(node, PageNode) else node.locked,
        "opacity": float(node.opacity),
        "transform": transform,
        "semantic": {"tags": list(node.semantic_tags)},
        "metadata": {"source_kind": node.kind},
    }
    if isinstance(node, TextNode):
        result["content"] = node.text
    if isinstance(node, ImageNode):
        result["asset_id"] = str(node.asset_id)
    return result


def _compile_descriptors(
    document: DesignIRDocument,
    descriptors: Iterable[CanvasOperationDescriptorRequest],
) -> list[DesignOperation]:
    nodes = node_index(document)
    operations: list[DesignOperation] = []
    for descriptor in descriptors:
        targets = [_uuid(value, "CANVAS_TARGET_ID_INVALID") for value in descriptor.target_ids]
        if descriptor.type == "CREATE_NODE":
            operations.append(_compile_create_frame(document, nodes, descriptor))
            continue
        if not targets:
            raise _bad_descriptor("CANVAS_TARGET_REQUIRED")
        for target_id in targets:
            node = nodes.get(target_id)
            if node is None:
                raise _bad_descriptor("CANVAS_TARGET_NOT_FOUND")
            if descriptor.type == "MOVE_NODE":
                x = _finite(descriptor.payload.get("x"), "CANVAS_MOVE_X_INVALID")
                y = _finite(descriptor.payload.get("y"), "CANVAS_MOVE_Y_INVALID")
                operations.append(
                    SetTransformOp(
                        node_id=target_id,
                        transform=node.transform.model_copy(update={"x": x, "y": y}),
                    )
                )
            elif descriptor.type == "RESIZE_NODE":
                width = _positive(descriptor.payload.get("width"), "CANVAS_WIDTH_INVALID")
                height = _positive(descriptor.payload.get("height"), "CANVAS_HEIGHT_INVALID")
                operations.append(
                    SetSizeOp(node_id=target_id, size=Size2D(width=width, height=height))
                )
            elif descriptor.type == "ROTATE_NODE":
                rotation = _finite(
                    descriptor.payload.get("rotation_deg"),
                    "CANVAS_ROTATION_INVALID",
                )
                operations.append(
                    SetTransformOp(
                        node_id=target_id,
                        transform=node.transform.model_copy(update={"rotation_deg": rotation}),
                    )
                )
            elif descriptor.type == "DELETE_NODE":
                operations.append(
                    RemoveNodeOp(
                        node_id=target_id,
                        recursive=bool(descriptor.payload.get("recursive", False)),
                    )
                )
            elif descriptor.type == "SET_TEXT":
                text_value = descriptor.payload.get("text")
                if not isinstance(text_value, str):
                    raise _bad_descriptor("CANVAS_TEXT_INVALID")
                operations.append(SetTextOp(node_id=target_id, text=text_value))
            elif descriptor.type == "REPLACE_ASSET":
                asset_id = _uuid(
                    descriptor.payload.get("asset_id"),
                    "CANVAS_ASSET_ID_INVALID",
                )
                operations.append(SetImageAssetOp(node_id=target_id, asset_id=asset_id))
            elif descriptor.type == "SET_PROPERTY":
                operations.extend(_compile_property(target_id, descriptor.payload))
            else:
                raise _bad_descriptor("CANVAS_OPERATION_UNSUPPORTED")
    return operations


def _compile_create_frame(
    document: DesignIRDocument,
    nodes: dict[UUID, Any],
    descriptor: CanvasOperationDescriptorRequest,
) -> AddNodeOp:
    payload = descriptor.payload
    kind = payload.get("kind", "FRAME")
    if kind != "FRAME":
        raise _bad_descriptor("CANVAS_CREATE_KIND_UNSUPPORTED")
    node_id = _uuid(payload.get("id"), "CANVAS_NEW_NODE_ID_INVALID")
    if node_id.version != 7:
        raise _bad_descriptor("CANVAS_NEW_NODE_ID_MUST_BE_UUID7")
    parent_id = _uuid(
        payload.get("parent_id", str(document.pages[0])),
        "CANVAS_PARENT_ID_INVALID",
    )
    parent = nodes.get(parent_id)
    if not isinstance(parent, (PageNode, FrameNode, GroupNode)):
        raise _bad_descriptor("CANVAS_PARENT_NOT_CONTAINER")
    width = _positive(payload.get("width"), "CANVAS_WIDTH_INVALID")
    height = _positive(payload.get("height"), "CANVAS_HEIGHT_INVALID")
    x = _finite(payload.get("x", 0), "CANVAS_X_INVALID")
    y = _finite(payload.get("y", 0), "CANVAS_Y_INVALID")
    name = payload.get("name", "Frame")
    if not isinstance(name, str) or not name.strip():
        raise _bad_descriptor("CANVAS_FRAME_NAME_INVALID")
    index = payload.get("index", len(parent.children))
    if not isinstance(index, int) or isinstance(index, bool) or index < 0:
        raise _bad_descriptor("CANVAS_FRAME_INDEX_INVALID")
    return AddNodeOp(
        parent_id=parent_id,
        index=index,
        node=FrameNode(
            id=node_id,
            parent_id=parent_id,
            name=name.strip(),
            size=Size2D(width=width, height=height),
            transform=Transform2D(x=x, y=y),
        ),
    )


def _compile_property(node_id: UUID, payload: dict[str, Any]) -> list[DesignOperation]:
    path = payload.get("path")
    value = payload.get("value")
    if path == "locked" and isinstance(value, bool):
        return [SetLockOp(node_id=node_id, locked=value)]
    if path == "visible" and isinstance(value, bool):
        return [SetAppearanceOp(node_id=node_id, visible=value)]
    if path == "opacity" and isinstance(value, (int, float)) and not isinstance(value, bool):
        opacity = float(value)
        if not math.isfinite(opacity) or not 0 <= opacity <= 1:
            raise _bad_descriptor("CANVAS_OPACITY_INVALID")
        return [SetAppearanceOp(node_id=node_id, opacity=opacity)]
    if path == "name" and isinstance(value, str) and value.strip():
        return [RenameNodeOp(node_id=node_id, name=value.strip())]
    raise _bad_descriptor("CANVAS_PROPERTY_UNSUPPORTED")


def _uuid(value: Any, code: str) -> UUID:
    try:
        return UUID(str(value))
    except (ValueError, TypeError, AttributeError) as exc:
        raise _bad_descriptor(code) from exc


def _finite(value: Any, code: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _bad_descriptor(code)
    number = float(value)
    if not math.isfinite(number):
        raise _bad_descriptor(code)
    return number


def _positive(value: Any, code: str) -> float:
    number = _finite(value, code)
    if number <= 0:
        raise _bad_descriptor(code)
    return number


def _bad_descriptor(code: str) -> ApiProblem:
    return ApiProblem(
        status=422,
        code=code.casefold(),
        title="Canvas command invalid",
        detail="The canvas command cannot be safely compiled into Design IR.",
    )


def _conflict(code: str) -> ApiProblem:
    return ApiProblem(
        status=409,
        code=code.casefold(),
        title="Canvas version conflict",
        detail=(
            "The DesignDocument changed since this canvas projection was loaded. "
            "Reload the canonical version before applying more edits."
        ),
    )


def _not_found() -> ApiProblem:
    return ApiProblem(
        status=404,
        code="canvas_document_not_found",
        title="Canvas document not found",
        detail="The requested tenant-scoped DesignDocument is unavailable.",
    )
