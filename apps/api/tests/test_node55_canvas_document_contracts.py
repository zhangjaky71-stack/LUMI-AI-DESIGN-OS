from __future__ import annotations

from lumi_api.api.v1.canvas_document_adapter import (
    _compile_descriptors,
    project_design_document,
)
from lumi_api.api.v1.canvas_document_schemas import CanvasOperationDescriptorRequest
from lumi_api.design_ir.document import DesignIRDocument, content_hash_sha256
from lumi_api.design_ir.nodes import FrameNode, PageNode
from lumi_api.design_ir.operations import AddNodeOp, SetSizeOp, SetTransformOp
from lumi_api.design_ir.primitives import Size2D, Transform2D
from lumi_api.domain.ids import new_uuid7


def document_with_frame() -> tuple[DesignIRDocument, str, str]:
    document_id = new_uuid7()
    page_id = new_uuid7()
    frame_id = new_uuid7()
    document = DesignIRDocument(
        document_id=document_id,
        revision=4,
        pages=(page_id,),
        nodes=(
            PageNode(
                id=page_id,
                name="Page 1",
                size=Size2D(width=1920, height=1080),
                children=(frame_id,),
            ),
            FrameNode(
                id=frame_id,
                parent_id=page_id,
                name="Hero",
                size=Size2D(width=750, height=1000),
                transform=Transform2D(x=10, y=20),
            ),
        ),
    )
    return document, str(page_id), str(frame_id)


def test_projection_preserves_canonical_identity_without_renderer_state() -> None:
    document, page_id, frame_id = document_with_frame()
    version_id = new_uuid7()
    projection = project_design_document(
        document=document,
        version_id=version_id,
        version_number=7,
        content_hash=content_hash_sha256(document),
    )
    assert projection.design_document_id == document.document_id
    assert projection.design_document_version_id == version_id
    assert projection.revision == 4
    assert projection.document["metadata"]["projection_schema"] == "lumi.canvas-projection/1.0"
    assert projection.document["nodes"][page_id]["metadata"]["source_kind"] == "page"
    assert projection.document["nodes"][frame_id]["transform"]["x"] == 10.0
    assert "svg" not in str(projection.document).lower()
    assert "pixi" not in str(projection.document).lower()


def test_move_and_resize_compile_to_absolute_python_operations() -> None:
    document, _, frame_id = document_with_frame()
    operations = _compile_descriptors(
        document,
        (
            CanvasOperationDescriptorRequest(
                type="MOVE_NODE",
                target_ids=[frame_id],
                payload={"x": 300, "y": 450},
            ),
            CanvasOperationDescriptorRequest(
                type="RESIZE_NODE",
                target_ids=[frame_id],
                payload={"width": 1080, "height": 1350},
            ),
        ),
    )
    assert isinstance(operations[0], SetTransformOp)
    assert operations[0].transform.x == 300
    assert operations[0].transform.y == 450
    assert isinstance(operations[1], SetSizeOp)
    assert operations[1].size.width == 1080
    assert operations[1].size.height == 1350


def test_create_frame_compiler_requires_uuid7_and_explicit_geometry() -> None:
    document, page_id, _ = document_with_frame()
    frame_id = new_uuid7()
    operations = _compile_descriptors(
        document,
        (
            CanvasOperationDescriptorRequest(
                type="CREATE_NODE",
                target_ids=[],
                payload={
                    "kind": "FRAME",
                    "id": str(frame_id),
                    "parent_id": page_id,
                    "name": "9:16 Frame",
                    "x": 100,
                    "y": 200,
                    "width": 1080,
                    "height": 1920,
                },
            ),
        ),
    )
    assert len(operations) == 1
    assert isinstance(operations[0], AddNodeOp)
    assert operations[0].node.id == frame_id
    assert operations[0].node.size.width == 1080
    assert operations[0].node.transform.y == 200
