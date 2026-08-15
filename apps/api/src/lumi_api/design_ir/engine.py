from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from .document import DesignIRDocument, content_hash_sha256, node_index
from .nodes import (
    DesignNode,
    FrameNode,
    GroupNode,
    ImageNode,
    PageNode,
    ShapeNode,
    TextNode,
    VectorNode,
)
from .operations import (
    AddNodeOp,
    DesignOperation,
    DesignOperationBatch,
    MoveNodeOp,
    RemoveNodeOp,
    RenameNodeOp,
    ReorderChildrenOp,
    SetAppearanceOp,
    SetFillOp,
    SetImageAssetOp,
    SetImageCropOp,
    SetLockOp,
    SetPageBackgroundOp,
    SetSizeOp,
    SetStrokeOp,
    SetTextOp,
    SetTextStyleOp,
    SetTransformOp,
)


class DesignIRError(ValueError):
    pass


class RevisionConflict(DesignIRError):
    pass


class OperationRejected(DesignIRError):
    pass


class ApplyResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    operation_id: UUID
    previous_revision: int
    new_revision: int
    content_hash: str
    changed_node_ids: tuple[UUID, ...]
    document: DesignIRDocument


def _container_children(node: DesignNode) -> tuple[UUID, ...]:
    if isinstance(node, (PageNode, FrameNode, GroupNode)):
        return node.children
    raise OperationRejected(f"node is not a container: {node.id}")


def _replace_node(node: DesignNode, **updates: Any) -> DesignNode:
    data = node.model_dump(mode="python")
    data.update(updates)
    return type(node).model_validate(data)  # type: ignore[return-value]


def _replace_children(node: DesignNode, children: tuple[UUID, ...]) -> DesignNode:
    _container_children(node)
    return _replace_node(node, children=children)


def _require_node(nodes: dict[UUID, DesignNode], node_id: UUID) -> DesignNode:
    node = nodes.get(node_id)
    if node is None:
        raise OperationRejected(f"node not found: {node_id}")
    return node


def _require_editable(node: DesignNode) -> None:
    if node.locked:
        raise OperationRejected(f"node is locked: {node.id}")


def _descendants(nodes: dict[UUID, DesignNode], node_id: UUID) -> set[UUID]:
    found: set[UUID] = set()
    stack = [node_id]
    while stack:
        current_id = stack.pop()
        current = _require_node(nodes, current_id)
        if isinstance(current, (PageNode, FrameNode, GroupNode)):
            for child_id in current.children:
                if child_id not in found:
                    found.add(child_id)
                    stack.append(child_id)
    return found


def _insert_child(
    parent: DesignNode, child_id: UUID, index: int
) -> DesignNode:
    children = list(_container_children(parent))
    if child_id in children:
        raise OperationRejected(f"child already exists in container: {child_id}")
    if index > len(children):
        raise OperationRejected(
            f"child index {index} exceeds container length {len(children)}"
        )
    children.insert(index, child_id)
    return _replace_children(parent, tuple(children))


def _remove_child(parent: DesignNode, child_id: UUID) -> DesignNode:
    children = list(_container_children(parent))
    if child_id not in children:
        raise OperationRejected(f"child is not in parent: {child_id}")
    children.remove(child_id)
    return _replace_children(parent, tuple(children))


def _apply_one(
    nodes: dict[UUID, DesignNode],
    operation: DesignOperation,
    changed: set[UUID],
) -> None:
    if isinstance(operation, AddNodeOp):
        if operation.node.id in nodes:
            raise OperationRejected(f"node already exists: {operation.node.id}")
        if isinstance(operation.node, PageNode):
            raise OperationRejected("add_node cannot create PageNode in v1")
        if operation.node.parent_id != operation.parent_id:
            raise OperationRejected("add_node parent_id must match node.parent_id")
        if isinstance(operation.node, (FrameNode, GroupNode)) and operation.node.children:
            raise OperationRejected("new container must be added with empty children")
        parent = _require_node(nodes, operation.parent_id)
        _require_editable(parent)
        nodes[operation.parent_id] = _insert_child(
            parent, operation.node.id, operation.index
        )
        nodes[operation.node.id] = operation.node
        changed.update({operation.parent_id, operation.node.id})
        return

    if isinstance(operation, RemoveNodeOp):
        node = _require_node(nodes, operation.node_id)
        if isinstance(node, PageNode):
            raise OperationRejected("remove_node cannot delete PageNode in v1")
        _require_editable(node)
        descendants = _descendants(nodes, node.id)
        if descendants and not operation.recursive:
            raise OperationRejected("container is not empty; recursive=true is required")
        for descendant_id in descendants:
            _require_editable(_require_node(nodes, descendant_id))
        assert node.parent_id is not None
        parent = _require_node(nodes, node.parent_id)
        _require_editable(parent)
        nodes[parent.id] = _remove_child(parent, node.id)
        removed = descendants | {node.id}
        for removed_id in removed:
            nodes.pop(removed_id, None)
        changed.update(removed | {parent.id})
        return

    if isinstance(operation, MoveNodeOp):
        node = _require_node(nodes, operation.node_id)
        if isinstance(node, PageNode):
            raise OperationRejected("move_node cannot move PageNode in v1")
        _require_editable(node)
        assert node.parent_id is not None
        old_parent = _require_node(nodes, node.parent_id)
        new_parent = _require_node(nodes, operation.new_parent_id)
        _require_editable(old_parent)
        _require_editable(new_parent)
        if operation.new_parent_id == node.id:
            raise OperationRejected("node cannot be its own parent")
        if operation.new_parent_id in _descendants(nodes, node.id):
            raise OperationRejected("move would create a scene graph cycle")

        old_without_node = _remove_child(old_parent, node.id)
        nodes[old_parent.id] = old_without_node

        insertion_parent = (
            nodes[new_parent.id]
            if new_parent.id != old_parent.id
            else old_without_node
        )
        nodes[new_parent.id] = _insert_child(
            insertion_parent, node.id, operation.index
        )
        nodes[node.id] = _replace_node(node, parent_id=new_parent.id)
        changed.update({node.id, old_parent.id, new_parent.id})
        return

    if isinstance(operation, ReorderChildrenOp):
        parent = _require_node(nodes, operation.parent_id)
        _require_editable(parent)
        current = _container_children(parent)
        if len(operation.child_ids) != len(set(operation.child_ids)):
            raise OperationRejected("reorder_children contains duplicate ids")
        if set(operation.child_ids) != set(current):
            raise OperationRejected(
                "reorder_children must contain exactly the current child ids"
            )
        nodes[parent.id] = _replace_children(parent, operation.child_ids)
        changed.add(parent.id)
        return

    node = _require_node(nodes, operation.node_id)

    if isinstance(operation, SetLockOp):
        nodes[node.id] = _replace_node(node, locked=operation.locked)
        changed.add(node.id)
        return

    _require_editable(node)

    if isinstance(operation, SetTransformOp):
        if isinstance(node, PageNode):
            raise OperationRejected("PageNode transform is not mutable in v1")
        nodes[node.id] = _replace_node(node, transform=operation.transform)
    elif isinstance(operation, SetSizeOp):
        if isinstance(node, GroupNode):
            raise OperationRejected("GroupNode has no explicit size")
        nodes[node.id] = _replace_node(node, size=operation.size)
    elif isinstance(operation, SetAppearanceOp):
        updates: dict[str, Any] = {}
        if operation.visible is not None:
            updates["visible"] = operation.visible
        if operation.opacity is not None:
            updates["opacity"] = operation.opacity
        nodes[node.id] = _replace_node(node, **updates)
    elif isinstance(operation, RenameNodeOp):
        nodes[node.id] = _replace_node(node, name=operation.name)
    elif isinstance(operation, SetTextOp):
        if not isinstance(node, TextNode):
            raise OperationRejected("set_text requires TextNode")
        nodes[node.id] = _replace_node(node, text=operation.text)
    elif isinstance(operation, SetTextStyleOp):
        if not isinstance(node, TextNode):
            raise OperationRejected("set_text_style requires TextNode")
        nodes[node.id] = _replace_node(node, style=operation.style)
    elif isinstance(operation, SetImageAssetOp):
        if not isinstance(node, ImageNode):
            raise OperationRejected("set_image_asset requires ImageNode")
        nodes[node.id] = _replace_node(node, asset_id=operation.asset_id)
    elif isinstance(operation, SetImageCropOp):
        if not isinstance(node, ImageNode):
            raise OperationRejected("set_image_crop requires ImageNode")
        nodes[node.id] = _replace_node(node, crop=operation.crop)
    elif isinstance(operation, SetFillOp):
        if not isinstance(node, (FrameNode, ShapeNode, VectorNode)):
            raise OperationRejected("set_fill requires Frame/Shape/Vector node")
        nodes[node.id] = _replace_node(node, fill=operation.fill)
    elif isinstance(operation, SetStrokeOp):
        if not isinstance(node, (FrameNode, ShapeNode, VectorNode)):
            raise OperationRejected("set_stroke requires Frame/Shape/Vector node")
        nodes[node.id] = _replace_node(node, stroke=operation.stroke)
    elif isinstance(operation, SetPageBackgroundOp):
        if not isinstance(node, PageNode):
            raise OperationRejected("set_page_background requires PageNode")
        nodes[node.id] = _replace_node(node, background=operation.background)
    else:
        raise OperationRejected(f"unsupported operation: {operation}")

    changed.add(node.id)


def apply_batch(
    document: DesignIRDocument, batch: DesignOperationBatch
) -> ApplyResult:
    if batch.document_id != document.document_id:
        raise OperationRejected("operation batch targets a different document")
    if batch.base_revision != document.revision:
        raise RevisionConflict(
            f"expected base revision {document.revision}, got {batch.base_revision}"
        )

    nodes = node_index(document)
    changed: set[UUID] = set()

    for operation in batch.operations:
        _apply_one(nodes, operation, changed)

    updated = DesignIRDocument(
        spec_version=document.spec_version,
        document_id=document.document_id,
        revision=document.revision + 1,
        coordinate_space=document.coordinate_space,
        pages=document.pages,
        nodes=tuple(nodes.values()),
        metadata=document.metadata,
    )

    return ApplyResult(
        operation_id=batch.operation_id,
        previous_revision=document.revision,
        new_revision=updated.revision,
        content_hash=content_hash_sha256(updated),
        changed_node_ids=tuple(sorted(changed, key=str)),
        document=updated,
    )
